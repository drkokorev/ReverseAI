"""Clean-zone implementation loop: plan, edit the workspace, run the oracle, repeat until green.

The released package is the only project data this module reads, through
``store.get_json(release_ref, Zone.CLEAN)``; the store refuses anything outside the clean and
released zones, so nothing from the dirty zone can reach the agents' prompts.
"""

from __future__ import annotations

import inspect
import io
import json
import shutil
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field

from reverseai.barrier.release import target_domains
from reverseai.barrier.sanitizer import mask_identity
from reverseai.implement.workspace import (
    ORACLE_FILES,
    ORACLE_RUNNER,
    ORACLE_SCENARIOS,
    WorkspaceError,
    safe_write,
    snapshot,
    workspace_files,
)
from reverseai.llm.gateway import Gateway
from reverseai.llm.jsonout import complete_json
from reverseai.llm.policy import DataPolicy
from reverseai.llm.types import Message
from reverseai.oracle import standalone
from reverseai.oracle.model import Scenario
from reverseai.project import Project
from reverseai.provenance.ledger import Ledger
from reverseai.sandbox.base import RunResult, Sandbox, free_port
from reverseai.spec.model import BehaviorSpec
from reverseai.spec.render import render_markdown
from reverseai.zones.store import Zone

_ACTOR = "clean.implement"
PLANNER_ACTOR = "clean.planner"
EXECUTOR_ACTOR = "clean.executor"
STILL_FAILING = "Tests are still failing; you are not done."
NO_TEST_RUN = "No test run yet."
MAX_FAILURE_LINES = 30
MAX_VALUE_CHARS = 120
CRASH_TAIL_LINES = 60
_MAX_PATH_ECHO = 200
_RUN_TIMEOUT_BASE_S = 60.0
_RUN_TIMEOUT_PER_SCENARIO_S = 60.0
_TEMPLATES = Path(__file__).parent / "templates"
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_MAX_ERROR_CHARS = 300
# The harness files, case-folded: on a case-insensitive filesystem (APFS) "Oracle_Runner.py"
# is the same file as "oracle_runner.py".
_PROTECTED = frozenset(name.casefold() for name in ORACLE_FILES)

_STACKS = {
    "python-fastapi": (
        "Python 3.12 with FastAPI. Only the standard library, fastapi, starlette, pydantic, "
        "uvicorn and httpx are available; nothing can be installed. The module `main` must "
        "expose the ASGI application as `app`."
    ),
}

_PLANNER_SYSTEM = """[role:planner]
You plan a clean-room implementation of a web application. You know the application only
through the behavior specification below; reproduce its observable HTTP behavior exactly.
Stack: {stack}
The application is started with `{app_cmd}` from the workspace root.
Reply with a concise numbered implementation plan in plain text: files, data model, endpoints,
validation order and error codes, and anything in the spec that is easy to get wrong."""

_EXECUTOR_SYSTEM = """[role:executor]
You write a clean-room implementation of a web application from a behavior specification,
an implementation plan and the results of acceptance tests. You see nothing else.
Stack: {stack}
The application is started with `{app_cmd}` from the workspace root, with a fresh process
for every test scenario.
Reply with JSON only, in this form:
{{"notes": "<short summary of this turn>",
  "edits": [{{"path": "<path relative to the workspace root>", "content": "<full file>"}}],
  "done": <true|false>}}
Every edit replaces the whole file. Absolute paths, '..' and the test harness files
({runner}, {scenarios}) are refused. Set "done" to true only when you believe every test
passes."""


class FileEdit(BaseModel):
    path: str
    content: str


class AgentTurn(BaseModel):
    notes: str = ""
    edits: list[FileEdit] = []
    done: bool = False


class ImplementConfig(BaseModel):
    max_iterations: int = Field(default=20, ge=1)
    stack: str = "python-fastapi"
    app_cmd: str = "uvicorn main:app"
    feedback: list[str] = []


class ImplementResult(BaseModel):
    iterations: int
    passed: bool
    total: int
    passed_count: int
    workspace: Path
    code_ref: str | None = None


@dataclass(frozen=True)
class _TestRun:
    passed: int
    total: int
    green: bool
    summary: str


def _template_dir(stack: str) -> Path:
    path = _TEMPLATES / stack
    if stack not in _STACKS or not path.is_dir():
        raise ValueError(f"unknown implementation stack {stack!r}")
    return path


def _seed_template(root: Path, template: Path) -> None:
    """Copy template files that the workspace does not have yet (earlier work is kept)."""
    for source in sorted(template.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        target = root / source.relative_to(template)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def _install_oracle(root: Path, scenarios_json: str) -> None:
    """(Re)write the harness files so the agent can never run a tampered oracle."""
    runner_source = Path(inspect.getsourcefile(standalone)).read_text(encoding="utf-8")
    for name, text in ((ORACLE_RUNNER, runner_source), (ORACLE_SCENARIOS, scenarios_json)):
        target = root / name
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        target.write_text(text, encoding="utf-8")


def _apply_edits(root: Path, edits: list[FileEdit]) -> list[str]:
    rejected: list[str] = []
    for edit in edits:
        try:
            if PurePosixPath(edit.path).as_posix().casefold() in _PROTECTED:
                raise WorkspaceError("protected file")
            safe_write(root, edit.path, edit.content)
        except WorkspaceError as exc:
            rejected.append(f"Rejected edit {edit.path[:_MAX_PATH_ECHO]}: {exc}")
    return rejected


Scrub = Callable[[str], str]


def _scrubber(root: Path, project: Project) -> Scrub:
    """Text cleaner for test output fed to the executor.

    The workspace root becomes ".", the interpreter prefixes "<python>" and the home directory
    "~", so no absolute host path (or project name inside one) reaches a prompt; brand and
    target domains are masked as the barrier masks them.
    """
    card = project.card
    domains = target_domains(project)
    replacements: list[tuple[str, str]] = []
    replacements.append((str(root.resolve()), "."))
    if root.is_absolute():  # a relative root would also match unrelated text
        replacements.append((str(root), "."))
    for prefix in (sys.prefix, sys.base_prefix):
        replacements += [(prefix, "<python>"), (str(Path(prefix).resolve()), "<python>")]
    replacements.append((str(Path.home()), "~"))
    # longest first, so a path is never half-replaced by one of its prefixes
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)

    def scrub(text: str) -> str:
        for old, new in replacements:
            if old and old != "/":
                text = text.replace(old, new)
        return mask_identity(
            text,
            brand_terms=card.brand_terms,
            product_name=card.product_name,
            target_domains=domains,
        )

    return scrub


def _short(value: Any, scrub: Scrub) -> str:
    text = scrub(repr(value))
    if len(text) <= MAX_VALUE_CHARS:
        return text
    return text[: MAX_VALUE_CHARS - 3] + "..."


def _failure_line(failure: dict, scrub: Scrub) -> str:
    pointer = scrub(str(failure.get("pointer") or "-"))
    return (
        f"- {failure.get('id')} step {failure.get('step')} {failure.get('kind')} {pointer}: "
        f"expected {_short(failure.get('expected'), scrub)}, "
        f"actual {_short(failure.get('actual'), scrub)}"
    )


def _parse_summary(stdout: str) -> dict | None:
    """The runner's one-line JSON summary (the last parseable one), or None."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(data, dict)
            and type(data.get("total")) is int
            and type(data.get("passed")) is int
            and isinstance(data.get("failed"), list)
        ):
            return data
    return None


def _evaluate(result: RunResult, expected_total: int, scrub: Scrub) -> _TestRun:
    """Score one oracle run; every text that goes back to the executor passes `scrub`."""
    data = _parse_summary(result.stdout)
    if data is None:
        reason = "timed out" if result.timed_out else f"exit code {result.exit_code}"
        summary = (
            f"passed 0/{expected_total}\n"
            f"The test runner output could not be parsed ({reason}). Last lines:\n"
            f"{scrub(result.tail(CRASH_TAIL_LINES))}"
        )
        return _TestRun(0, expected_total, False, summary)
    passed, total = data["passed"], data["total"]
    failures = [f for f in data["failed"] if isinstance(f, dict)][:MAX_FAILURE_LINES]
    lines = [f"passed {passed}/{total}", *(_failure_line(f, scrub) for f in failures)]
    green = total == expected_total and passed == total
    return _TestRun(passed, total, green, "\n".join(lines))


def _run_oracle(
    sandbox: Sandbox,
    root: Path,
    config: ImplementConfig,
    scenarios_json: str,
    count: int,
    scrub: Scrub,
) -> _TestRun:
    _install_oracle(root, scenarios_json)
    cmd = [
        "python",
        "-I",  # the workspace is agent-written: never let it shadow the runner's imports
        ORACLE_RUNNER,
        ORACLE_SCENARIOS,
        "--app",
        config.app_cmd,
        "--port",
        str(free_port()),
    ]
    timeout = _RUN_TIMEOUT_BASE_S + _RUN_TIMEOUT_PER_SCENARIO_S * count
    return _evaluate(sandbox.run(cmd, timeout=timeout), count, scrub)


def _planner_prompt(spec_md: str, feedback: list[str]) -> str:
    parts = ["# Behavior specification", spec_md]
    if feedback:
        parts += ["# Acceptance feedback", "\n".join(f"- {line}" for line in feedback)]
    return "\n\n".join(parts)


def _executor_prompt(
    *,
    claimed_done: bool,
    spec_md: str,
    plan: str,
    feedback: list[str],
    workspace: str,
    rejected: list[str],
    last_summary: str | None,
) -> str:
    parts = [STILL_FAILING] if claimed_done else []
    parts += ["# Behavior specification", spec_md, "# Implementation plan", plan]
    if feedback:
        parts += ["# Acceptance feedback", "\n".join(f"- {line}" for line in feedback)]
    parts += ["# Current workspace", workspace]
    if rejected:
        parts += ["# Rejected edits", "\n".join(rejected)]
    parts += ["# Last test run", last_summary or NO_TEST_RUN]
    return "\n\n".join(parts)


def _zip_workspace(root: Path) -> bytes:
    """Deterministic zip of the agent's code (harness files and caches excluded)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in workspace_files(root):
            info = zipfile.ZipInfo(rel.as_posix(), date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, (root / rel).read_bytes())
    return buffer.getvalue()


def _loop(
    gateway: Gateway,
    sandbox: Sandbox,
    root: Path,
    config: ImplementConfig,
    fmt: dict[str, str],
    spec_md: str,
    scenarios_json: str,
    count: int,
    scrub: Scrub,
    ledger: Ledger,
    policy: DataPolicy,
    progress: list[int],
) -> tuple[_TestRun | None, int]:
    """Planner once, then executor turns and oracle runs until green or out of iterations.

    ``progress[0]`` is the iteration in progress, readable when this raises.
    """
    plan = gateway.complete(
        "planner",
        [Message(role="user", content=_planner_prompt(spec_md, config.feedback))],
        system=_PLANNER_SYSTEM.format(**fmt),
        policy=policy,
        zone=Zone.CLEAN,
        actor=PLANNER_ACTOR,
    ).text.strip()

    executor_system = _EXECUTOR_SYSTEM.format(**fmt)
    last_summary: str | None = None
    rejected: list[str] = []
    claimed_done = False
    run: _TestRun | None = None
    iterations = 0
    for iteration in range(1, config.max_iterations + 1):
        iterations = progress[0] = iteration
        prompt = _executor_prompt(
            claimed_done=claimed_done,
            spec_md=spec_md,
            plan=plan,
            feedback=config.feedback,
            workspace=snapshot(root),
            rejected=rejected,
            last_summary=last_summary,
        )
        turn: AgentTurn = complete_json(
            gateway,
            "executor",
            [Message(role="user", content=prompt)],
            model_cls=AgentTurn,
            system=executor_system,
            policy=policy,
            zone=Zone.CLEAN,
            actor=EXECUTOR_ACTOR,
        )
        rejected = _apply_edits(root, turn.edits)
        run = _run_oracle(sandbox, root, config, scenarios_json, count, scrub)
        ledger.append(
            "implement.iteration",
            Zone.CLEAN.value,
            _ACTOR,
            {
                "iteration": iteration,
                "passed": run.passed,
                "total": run.total,
                "rejected_edits": len(rejected),
            },
        )
        if run.green:
            break
        last_summary = run.summary
        claimed_done = turn.done
    return run, iterations


def implement(
    project: Project,
    release_ref: str,
    gateway: Gateway,
    sandbox: Sandbox,
    config: ImplementConfig,
) -> ImplementResult:
    """Implement the released package in ``sandbox.workdir`` until the oracle passes."""
    # The only read of project data in the clean zone.
    package = project.store.get_json(release_ref, Zone.CLEAN)
    spec = BehaviorSpec.model_validate(package["spec"])
    scenarios = [Scenario.model_validate(s) for s in package["scenarios"]]
    template = _template_dir(config.stack)

    ledger = project.ledger
    policy = project.card.data_policy
    root = Path(sandbox.workdir)
    root.mkdir(parents=True, exist_ok=True)
    _seed_template(root, template)
    scenarios_json = json.dumps(
        [s.model_dump(mode="json") for s in scenarios], ensure_ascii=False, indent=2
    )
    _install_oracle(root, scenarios_json)
    ledger.append(
        "implement.start",
        Zone.CLEAN.value,
        _ACTOR,
        {
            "release_ref": release_ref,
            "scenarios": len(scenarios),
            "sandbox_isolated": bool(getattr(sandbox, "isolated", False)),
        },
    )
    scrub = _scrubber(root, project)

    fmt = {
        "stack": _STACKS[config.stack],
        "app_cmd": config.app_cmd,
        "runner": ORACLE_RUNNER,
        "scenarios": ORACLE_SCENARIOS,
    }
    progress = [0]
    try:
        run, iterations = _loop(
            gateway, sandbox, root, config, fmt, render_markdown(spec), scenarios_json,
            len(scenarios), scrub, ledger, policy, progress,
        )
    except BaseException as exc:
        # The run ends without a result (e.g. the executor never produced valid JSON): the
        # ledger still closes it, so an auditor never sees a start without an end.
        ledger.append(
            "implement.done",
            Zone.CLEAN.value,
            _ACTOR,
            {
                "passed": False,
                "iterations": progress[0],
                "code_ref": None,
                "error": f"{type(exc).__name__}: {exc}"[:_MAX_ERROR_CHARS],
            },
        )
        raise

    passed = run is not None and run.green
    code = project.store.put(Zone.CLEAN, "code", "workspace.zip", _zip_workspace(root))
    ledger.append(
        "implement.done",
        Zone.CLEAN.value,
        _ACTOR,
        {"passed": passed, "iterations": iterations, "code_ref": code.id},
    )
    return ImplementResult(
        iterations=iterations,
        passed=passed,
        total=len(scenarios),
        passed_count=run.passed if run is not None else 0,
        workspace=root,
        code_ref=code.id,
    )
