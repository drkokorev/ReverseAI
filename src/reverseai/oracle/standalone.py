"""Dependency-light behavior oracle runner (stdlib + httpx only).

This file is copied verbatim into implementation sandboxes, so it must never import
`reverseai`. It operates on plain dicts shaped like `reverseai.oracle.model.Scenario.model_dump()`.

CLI:
    python standalone.py scenarios.json --app "uvicorn main:app" --port 8000

The app is started fresh for every scenario (reset by restart) and one JSON summary line
`{"total", "passed", "failed"}` is printed to stdout. Exit code is 0 only when all passed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

VOLATILE = "<volatile>"
REQUEST_TIMEOUT_S = 10.0
STARTUP_TIMEOUT_S = 30.0
STOP_TIMEOUT_S = 5.0
MAX_REPORTED_FAILURES = 30
_ERROR_TEXT_LIMIT = 300

_DATETIME_PREFIX = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", re.ASCII)
_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE | re.ASCII,
)
_PATH_VAR = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


# --- normalization ------------------------------------------------------------------------


def _parse_datetime(value: str) -> bool:
    text = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_volatile(value: Any) -> bool:
    """True for ISO date-time strings and UUID strings (values that differ run to run)."""
    if not isinstance(value, str):
        return False
    if _UUID.fullmatch(value):
        return True
    return bool(_DATETIME_PREFIX.match(value)) and _parse_datetime(value)


def normalize(obj: Any) -> Any:
    """Recursively replace volatile values with `"<volatile>"`."""
    if isinstance(obj, dict):
        return {key: normalize(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [normalize(item) for item in obj]
    return VOLATILE if is_volatile(obj) else obj


def json_equal(a: Any, b: Any) -> bool:
    """JSON value equality that never treats booleans as numbers."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(
            json_equal(x, y) for x, y in zip(a, b, strict=True)
        )
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        return False
    return a == b


# --- JSON pointer (RFC 6901) --------------------------------------------------------------


def escape_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def resolve_pointer(doc: Any, pointer: str) -> tuple[bool, Any]:
    """Return (found, value) for an RFC 6901 pointer; `""` is the whole document."""
    if pointer == "":
        return True, doc
    if not pointer.startswith("/"):
        return False, None
    current = doc
    for raw in pointer[1:].split("/"):
        token = _unescape_token(raw)
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                return False, None
            index = int(token)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


# --- shape checks -------------------------------------------------------------------------


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(expected: str, value: Any) -> bool:
    actual = _type_name(value)
    if expected == "number":
        return actual in ("integer", "number")
    return actual == expected


def _shape_violations(
    schema: dict, value: Any, pointer: str, out: list[tuple[str, str, str]]
) -> None:
    if not isinstance(schema, dict) or not schema:
        return
    expected_type = schema.get("type")
    if expected_type is not None:
        types = (
            [expected_type] if isinstance(expected_type, str) else list(expected_type)
        )
        if not any(_matches_type(t, value) for t in types):
            out.append((pointer, "|".join(types), _type_name(value)))
            return
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                out.append((f"{pointer}/{escape_token(key)}", "present", "missing"))
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                _shape_violations(
                    sub, value[key], f"{pointer}/{escape_token(key)}", out
                )
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _shape_violations(schema["items"], item, f"{pointer}/{index}", out)
    if (
        schema.get("format") == "date-time"
        and isinstance(value, str)
        and not _parse_datetime(value)
    ):
        out.append((pointer, "date-time", "string"))


def check_shape(schema: dict, value: Any) -> list[str]:
    """Return the JSON pointers at which `value` violates the inferred `schema` subset."""
    out: list[tuple[str, str, str]] = []
    _shape_violations(schema, value, "", out)
    return [pointer for pointer, _, _ in out]


# --- scenario execution -------------------------------------------------------------------


def _failure(
    step: int, kind: str, pointer: str | None, expected: Any, actual: Any
) -> dict:
    return {
        "step": step,
        "kind": kind,
        "pointer": pointer,
        "expected": expected,
        "actual": actual,
    }


def _substitute(path: str, variables: dict[str, Any]) -> tuple[str, str | None]:
    """Fill `{name}` placeholders; return (path, first missing variable name or None)."""
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            missing.append(name)
            return match.group(0)
        return quote(str(variables[name]), safe="")

    filled = _PATH_VAR.sub(replace, path)
    return filled, (missing[0] if missing else None)


def _response_json(response: httpx.Response) -> Any:
    if not response.content.strip():
        return None
    try:
        return response.json()
    except ValueError:
        return None


def run_scenario(base_url: str, scenario: dict, client: Any) -> dict:
    """Run one scenario dict against `base_url` using an httpx-like `client`."""
    failures: list[dict] = []
    variables: dict[str, Any] = {}
    base = base_url.rstrip("/")
    for index, scenario_step in enumerate(scenario.get("steps", [])):
        step = scenario_step["step"]
        expect = scenario_step["expect"]
        path, missing = _substitute(step["path"], variables)
        if missing is not None:
            failures.append(_failure(index, "error", None, missing, None))
            break
        kwargs: dict[str, Any] = {}
        if step.get("json_body") is not None:
            kwargs["json"] = step["json_body"]
        try:
            response = client.request(step["method"], base + path, **kwargs)
        except httpx.HTTPError as exc:
            text = f"{type(exc).__name__}: {exc}"[:_ERROR_TEXT_LIMIT]
            failures.append(_failure(index, "error", None, "response", text))
            break
        body = _response_json(response)

        if response.status_code != expect["status"]:
            failures.append(
                _failure(index, "status", None, expect["status"], response.status_code)
            )
        else:
            schema = expect.get("json_shape")
            if schema:
                violations: list[tuple[str, str, str]] = []
                _shape_violations(schema, body, "", violations)
                for pointer, expected_desc, actual_desc in violations:
                    failures.append(
                        _failure(index, "shape", pointer, expected_desc, actual_desc)
                    )
            for pointer, expected in (expect.get("json_equals") or {}).items():
                found, actual = resolve_pointer(body, pointer)
                if not found or not json_equal(actual, expected):
                    failures.append(_failure(index, "value", pointer, expected, actual))

        for name, pointer in (step.get("save") or {}).items():
            found, value = resolve_pointer(body, pointer)
            if found:
                variables[name] = value
    return {"id": scenario.get("id"), "passed": not failures, "failures": failures}


# --- CLI ----------------------------------------------------------------------------------


def _app_argv(app: str, port: int) -> list[str]:
    parts = shlex.split(app)
    if parts and parts[0] == "uvicorn":
        return [
            sys.executable,
            "-m",
            "uvicorn",
            *parts[1:],
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
        ]
    return parts


def _start_app(app: str, port: int, log: Any) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        _app_argv(app, port),
        env={**os.environ, "PORT": str(port)},
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _signal_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass  # the group is gone already


def _stop_app(proc: subprocess.Popen[bytes]) -> None:
    """Stop the app and everything it started (its own process group).

    The group is signalled even when the leader already exited: a worker or a background child
    it left behind would otherwise keep the port and outlive the run.
    """
    _signal_group(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        pass
    _signal_group(proc.pid, signal.SIGKILL)  # stragglers that ignored SIGTERM
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        pass


def _wait_ready(base_url: str, proc: subprocess.Popen[bytes], timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    with httpx.Client(trust_env=False, timeout=2.0) as probe:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return False
            try:
                probe.get(base_url + "/")
                return True
            except httpx.HTTPError:
                time.sleep(0.1)
    return False


def _log_tail(log: Any) -> str:
    log.flush()
    log.seek(0)
    return log.read().decode("utf-8", errors="replace")[-_ERROR_TEXT_LIMIT:]


def _run_isolated(
    scenario: dict, app: str, port: int, startup_timeout_s: float
) -> dict:
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryFile() as log:
        proc = _start_app(app, port, log)
        try:
            if not _wait_ready(base_url, proc, startup_timeout_s):
                failure = _failure(
                    0, "error", None, "app did not start", _log_tail(log)
                )
                return {
                    "id": scenario.get("id"),
                    "passed": False,
                    "failures": [failure],
                }
            with httpx.Client(trust_env=False, timeout=REQUEST_TIMEOUT_S) as client:
                return run_scenario(base_url, scenario, client)
        finally:
            _stop_app(proc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run oracle scenarios against an app.")
    parser.add_argument(
        "scenarios", help="path to scenarios JSON (a list of scenarios)"
    )
    parser.add_argument(
        "--app", required=True, help='app command, e.g. "uvicorn main:app"'
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--startup-timeout", type=float, default=STARTUP_TIMEOUT_S)
    args = parser.parse_args(argv)

    with open(args.scenarios, encoding="utf-8") as fh:
        data = json.load(fh)
    scenarios = data["scenarios"] if isinstance(data, dict) else data

    passed = 0
    failed: list[dict] = []
    for scenario in scenarios:
        try:
            result = _run_isolated(scenario, args.app, args.port, args.startup_timeout)
        except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
            # The app command cannot run, or the scenario is malformed: one failed scenario,
            # and the summary line is still printed.
            sid = scenario.get("id") if isinstance(scenario, dict) else None
            text = f"{type(exc).__name__}: {exc}"[:_ERROR_TEXT_LIMIT]
            failure = _failure(0, "error", None, "scenario run", text)
            result = {"id": sid, "passed": False, "failures": [failure]}
        if result["passed"]:
            passed += 1
        elif len(failed) < MAX_REPORTED_FAILURES:
            failed.append({"id": result["id"], **result["failures"][0]})
    print(
        json.dumps({"total": len(scenarios), "passed": passed, "failed": failed}),
        flush=True,
    )
    return 0 if passed == len(scenarios) else 1


if __name__ == "__main__":
    sys.exit(main())
