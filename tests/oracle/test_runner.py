import ast
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from reverseai.bench.server import load_target, serve_asgi
from reverseai.observe.contracts import infer_endpoints
from reverseai.observe.har import Exchange
from reverseai.oracle import standalone
from reverseai.oracle.build import build_scenarios
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.oracle.runner import ScenarioResult, StepFailure, run_scenarios

taskboard = load_target("taskboard")

SCRIPT: list[tuple[str, str, Any]] = [
    ("POST", "/api/tasks", {"title": "write report", "priority": "high"}),
    ("POST", "/api/tasks", {"title": "write report"}),  # 409 duplicate
    ("GET", "/api/tasks/1", None),
    ("PATCH", "/api/tasks/1", {"done": True}),
    ("GET", "/api/tasks", None),
    ("GET", "/api/stats", None),
    ("DELETE", "/api/tasks/1", None),
    ("GET", "/api/tasks/1", None),
    ("POST", "/api/tasks", {"title": ""}),
    ("POST", "/api/tasks", {"title": "   "}),
    ("POST", "/api/tasks", {"title": "x", "priority": "urgent"}),
    ("GET", "/api/tasks/999", None),
    ("PATCH", "/api/tasks/999", {"done": True}),
]


def record(client: httpx.Client, base_url: str) -> list[Exchange]:
    exchanges = []
    for i, (method, path, body) in enumerate(SCRIPT):
        r = client.request(method, path, json=body)
        exchanges.append(
            Exchange(
                id=f"x{i}",
                method=method,
                url=base_url + path,
                path=path,
                query={},
                status=r.status_code,
                request_json=body,
                response_json=r.json() if r.content else None,
                response_content_type=r.headers.get("content-type", ""),
            )
        )
    return exchanges


@pytest.fixture(scope="module")
def taskboard_server():
    app = taskboard.create_app()
    with serve_asgi(app) as url:
        yield app, url


def test_runner_passes_on_taskboard(taskboard_server) -> None:
    app, url = taskboard_server
    taskboard.reset_state(app)
    with httpx.Client(base_url=url, trust_env=False) as client:
        exchanges = record(client, url)
    scenarios = build_scenarios(exchanges, infer_endpoints(exchanges))
    assert len(scenarios) >= 5
    assert any(len(s.steps) >= 4 for s in scenarios)
    [duplicate] = [s for s in scenarios if "→ 409" in s.title]
    assert duplicate.steps[0].expect.status == 201
    assert duplicate.steps[1].expect.json_equals == {"/error": "duplicate"}

    results = run_scenarios(scenarios, url, reset=lambda: taskboard.reset_state(app))
    assert [r.id for r in results] == [s.id for s in scenarios]
    assert all(isinstance(r, ScenarioResult) for r in results)
    assert [r.failures for r in results if not r.passed] == []


def test_runner_reports_status_failure(taskboard_server) -> None:
    app, url = taskboard_server
    scenario = Scenario(
        id="s001",
        title="GET /api/tasks/{id} → 200",
        steps=[
            ScenarioStep(
                step=Step(method="GET", path="/api/tasks/999"),
                expect=Expect(status=200),
            )
        ],
    )
    [result] = run_scenarios([scenario], url, reset=lambda: taskboard.reset_state(app))
    assert result.passed is False
    assert result.failures == [
        StepFailure(step=0, kind="status", pointer=None, expected=200, actual=404)
    ]


def test_runner_reports_shape_value_and_missing_variable(taskboard_server) -> None:
    app, url = taskboard_server
    calls = []
    scenario = Scenario(
        id="s007",
        title="t",
        steps=[
            ScenarioStep(
                step=Step(
                    method="POST",
                    path="/api/tasks",
                    json_body={"title": "a"},
                    save={"v0": "/nope"},
                ),
                expect=Expect(
                    status=201,
                    json_shape={
                        "type": "object",
                        "properties": {"title": {"type": "integer"}},
                        "required": ["owner"],
                    },
                    json_equals={"/title": "b", "/missing": 1},
                ),
            ),
            ScenarioStep(
                step=Step(method="GET", path="/api/tasks/{v0}"),
                expect=Expect(status=200),
            ),
        ],
    )
    [result] = run_scenarios(
        [scenario], url, reset=lambda: calls.append(taskboard.reset_state(app))
    )
    assert len(calls) == 1
    kinds = [(f.step, f.kind, f.pointer) for f in result.failures]
    assert kinds == [
        (0, "shape", "/owner"),
        (0, "shape", "/title"),
        (0, "value", "/title"),
        (0, "value", "/missing"),
        (1, "error", None),
    ]
    assert result.failures[0].actual == "missing"
    assert result.failures[1].expected == "integer"
    assert result.failures[1].actual == "string"
    assert result.failures[2].expected == "b"
    assert result.failures[2].actual == "a"
    assert result.failures[4].expected == "v0"


def test_runner_reports_transport_error() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    scenario = Scenario(
        id="s001",
        title="t",
        steps=[
            ScenarioStep(
                step=Step(method="GET", path="/api/stats"), expect=Expect(status=200)
            )
        ],
    )
    [result] = run_scenarios([scenario], f"http://127.0.0.1:{port}")
    assert [(f.step, f.kind) for f in result.failures] == [(0, "error")]


def test_standalone_imports_only_stdlib_and_httpx() -> None:
    tree = ast.parse(Path(standalone.__file__).read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots.add((node.module or "").split(".")[0])
    roots.discard("__future__")
    assert roots - set(sys.stdlib_module_names) == {"httpx"}


MINI_APP = """
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()
items = {}


@app.get("/")
def root():
    return {"ok": True}


@app.post("/items")
def create(body: dict):
    item = {"id": len(items) + 1, "name": body["name"]}
    items[item["id"]] = item
    return JSONResponse(item, status_code=201)


@app.get("/items/{item_id}")
def get(item_id: int):
    if item_id not in items:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return items[item_id]
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _scenario(id: str, steps: list[ScenarioStep]) -> dict:
    return Scenario(id=id, title=id, steps=steps).model_dump()


def _run_cli(
    tmp_path: Path, scenarios: list[dict], app: str
) -> subprocess.CompletedProcess[str]:
    shutil.copy(standalone.__file__, tmp_path / "oracle_runner.py")
    (tmp_path / "scenarios.json").write_text(json.dumps(scenarios))
    return subprocess.run(
        [
            sys.executable,
            "oracle_runner.py",
            "scenarios.json",
            "--app",
            app,
            "--port",
            str(_free_port()),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_standalone_main_restarts_app_per_scenario(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(MINI_APP)
    create_then_get = [
        ScenarioStep(
            step=Step(
                method="POST",
                path="/items",
                json_body={"name": "n"},
                save={"v0": "/id"},
            ),
            expect=Expect(status=201, json_equals={"/id": 1, "/name": "n"}),
        ),
        ScenarioStep(
            step=Step(method="GET", path="/items/{v0}"),
            expect=Expect(
                status=200,
                json_shape={"type": "object", "required": ["id", "name"]},
                json_equals={"/name": "n"},
            ),
        ),
    ]
    wrong = [
        ScenarioStep(
            step=Step(method="GET", path="/items/5"), expect=Expect(status=200)
        )
    ]
    scenarios = [
        _scenario("s001", create_then_get),
        _scenario("s002", wrong),
        # passes only if the app was restarted (ids start at 1 again)
        _scenario("s003", create_then_get),
    ]
    proc = _run_cli(tmp_path, scenarios, "uvicorn main:app")
    assert proc.returncode == 1, proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary == {
        "total": 3,
        "passed": 2,
        "failed": [
            {
                "id": "s002",
                "step": 0,
                "kind": "status",
                "pointer": None,
                "expected": 200,
                "actual": 404,
            }
        ],
    }


def test_standalone_main_all_green_exits_zero(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(MINI_APP)
    ok = [
        ScenarioStep(
            step=Step(method="GET", path="/items/1"), expect=Expect(status=404)
        )
    ]
    proc = _run_cli(tmp_path, [_scenario("s001", ok)], "uvicorn main:app")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == {
        "total": 1,
        "passed": 1,
        "failed": [],
    }


def test_standalone_main_reports_app_that_does_not_start(tmp_path: Path) -> None:
    ok = [ScenarioStep(step=Step(method="GET", path="/"), expect=Expect(status=200))]
    app = f'"{sys.executable}" -c "raise SystemExit(3)"'
    proc = _run_cli(tmp_path, [_scenario("s001", ok)], app)
    assert proc.returncode == 1
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["total"] == 1 and summary["passed"] == 0
    [failure] = summary["failed"]
    assert failure["id"] == "s001"
    assert failure["kind"] == "error"
    assert failure["expected"] == "app did not start"


# --- final review fixes --------------------------------------------------------------------


def test_run_scenarios_throttles_requests() -> None:
    import itertools
    import time

    sent: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(time.monotonic())
        return httpx.Response(200, json={})

    scenario = Scenario(id="s", title="t", steps=[
        ScenarioStep(step=Step(method="GET", path="/a"), expect=Expect(status=200))
        for _ in range(3)
    ])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        run_scenarios([scenario, scenario], "http://t", client=client, delay_s=0.05)
    gaps = [b - a for a, b in itertools.pairwise(sent)]
    assert len(sent) == 6 and min(gaps) >= 0.045


# --- audit 2026-10-22 ------------------------------------------------------------------------


def test_stop_app_kills_the_group_even_when_the_leader_already_exited(tmp_path: Path) -> None:
    import os
    import time

    pid_file = tmp_path / "child.pid"
    proc = subprocess.Popen(
        ["sh", "-c", f"sleep 60 & echo $! > {pid_file}"], start_new_session=True
    )
    proc.wait(timeout=10)
    child = int(pid_file.read_text().strip())
    os.kill(child, 0)  # the background child outlived its group leader
    standalone._stop_app(proc)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        os.kill(child, 9)
        raise AssertionError("the leader's child survived _stop_app")


def test_standalone_main_reports_an_app_command_that_cannot_run(tmp_path: Path) -> None:
    ok = [ScenarioStep(step=Step(method="GET", path="/"), expect=Expect(status=200))]
    proc = _run_cli(tmp_path, [_scenario("s001", ok)], str(tmp_path / "no-such-binary"))
    assert proc.returncode == 1
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert (summary["total"], summary["passed"]) == (1, 0)
    [failure] = summary["failed"]
    assert (failure["id"], failure["kind"]) == ("s001", "error")


def test_standalone_main_reports_a_malformed_scenario_and_goes_on(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(MINI_APP)
    ok = [ScenarioStep(step=Step(method="GET", path="/items/1"), expect=Expect(status=404))]
    bad = {"id": "bad", "title": "bad", "steps": [{"expect": {"status": 200}}]}
    proc = _run_cli(tmp_path, [bad, _scenario("s002", ok), "not a scenario"], "uvicorn main:app")
    assert proc.returncode == 1, proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert (summary["total"], summary["passed"]) == (3, 1)
    assert [(f["id"], f["kind"]) for f in summary["failed"]] == [("bad", "error"), (None, "error")]
