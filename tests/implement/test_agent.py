import inspect
import io
import json
import zipfile
from pathlib import Path

import pytest

from reverseai.config import load_settings
from reverseai.implement.agent import (
    AgentTurn,
    FileEdit,
    ImplementConfig,
    implement,
)
from reverseai.llm.gateway import Gateway
from reverseai.llm.providers import FakeProvider
from reverseai.llm.types import LLMRequest
from reverseai.oracle import standalone
from reverseai.sandbox import LocalSandbox, RunResult
from reverseai.zones.store import Zone, ZoneViolation

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TARGET_HOST = "app.example.com"  # the target host of the `project` fixture in conftest.py
FAKE_CLONE = (FIXTURES / "fake_clone" / "main.py").read_text(encoding="utf-8")
BROKEN_MAIN = "from fastapi import FastAPI\n\napp = FastAPI()\n"
PLAN = "1. Keep tasks in a dict.\n2. Validate in the documented order."
STILL_FAILING = "Tests are still failing; you are not done."


def turn(*edits: tuple[str, str], done: bool = False, notes: str = "") -> str:
    return AgentTurn(
        notes=notes, edits=[FileEdit(path=p, content=c) for p, c in edits], done=done
    ).model_dump_json()


def summary(total: int, passed: int, failed: list[dict] | None = None) -> RunResult:
    line = json.dumps({"total": total, "passed": passed, "failed": failed or []})
    return RunResult(0 if passed == total else 1, line + "\n", "", False)


class ScriptedSandbox:
    """Sandbox double: returns canned oracle runs, records the commands it was given."""

    isolated = False

    def __init__(self, workdir: Path, results: list[RunResult]):
        self.workdir = workdir
        self.results = list(results)
        self.cmds: list[list[str]] = []

    def run(self, cmd, *, timeout=600):
        self.cmds.append(list(cmd))
        return self.results.pop(0)

    def start(self, cmd, *, port, ready_path="/", timeout=30):
        raise AssertionError("implement must not start services itself")


def make_gateway(project, executor_turns: list[str], plan: str = PLAN):
    turns = list(executor_turns)

    def responder(req: LLMRequest) -> str:
        system = req.system or ""
        if system.startswith("[role:planner]"):
            return plan
        if system.startswith("[role:executor]"):
            return turns.pop(0)
        raise AssertionError(f"unexpected system prompt: {system[:40]!r}")

    fake = FakeProvider(name="anthropic", responder=responder)
    return Gateway(load_settings(), {"anthropic": fake}, project.ledger), fake


def executor_prompts(fake: FakeProvider) -> list[str]:
    return [
        r.messages[0].content
        for r in fake.requests
        if (r.system or "").startswith("[role:executor]")
    ]


def events(project, type_: str):
    return [e for e in project.ledger.events() if e.type == type_]


def test_implement_reaches_green_with_scripted_executor(released_project, tmp_path):
    project, ref = released_project
    gw, fake = make_gateway(project, [
        turn(("main.py", BROKEN_MAIN), ("../outside.py", "x = 1\n"), done=True),
        turn(("main.py", FAKE_CLONE), done=True),
    ])
    ws = tmp_path / "ws"

    res = implement(project, ref, gw, LocalSandbox(ws), ImplementConfig(max_iterations=3))
    reads = [e.payload for e in events(project, "artifact.read") if e.payload["reader"] == "clean"]
    assert [r["id"] for r in reads] == [ref]  # the release package is the only read

    assert res.passed and res.iterations == 2
    assert (res.total, res.passed_count) == (4, 4)
    assert res.workspace == ws
    assert not (tmp_path / "outside.py").exists()

    systems = [(r.system or "").split("]")[0] + "]" for r in fake.requests]
    assert systems == ["[role:planner]", "[role:executor]", "[role:executor]"]
    first, second = executor_prompts(fake)
    assert PLAN in first and "Tasklet" in first and "title_too_long" in first
    assert "No test run yet." in first
    assert second.startswith(STILL_FAILING)
    assert "passed 0/4" in second
    assert "S-001 step 0 status" in second
    assert "Rejected edit ../outside.py:" in second
    assert "=== main.py ===\n" + BROKEN_MAIN in second
    for request in fake.requests:
        prompt = (request.system or "") + "".join(m.content for m in request.messages)
        assert TARGET_HOST not in prompt
        assert "oracle_runner" not in prompt.split("# Current workspace")[-1]

    code = project.store.ref(res.code_ref, Zone.CLEAN)
    assert (code.kind, code.name) == ("code", "workspace.zip")
    with zipfile.ZipFile(io.BytesIO(project.store.get(res.code_ref, Zone.CLEAN))) as zf:
        names = zf.namelist()
        assert zf.read("main.py").decode("utf-8") == FAKE_CLONE
    assert "requirements.txt" in names
    assert not {"oracle_runner.py", "oracle_scenarios.json"} & set(names)
    assert not any("__pycache__" in n for n in names)

    start, = events(project, "implement.start")
    assert start.zone == "clean"
    assert start.payload == {"release_ref": ref, "scenarios": 4, "sandbox_isolated": False}
    iterations = [e.payload for e in events(project, "implement.iteration")]
    assert iterations == [
        {"iteration": 1, "passed": 0, "total": 4, "rejected_edits": 1},
        {"iteration": 2, "passed": 4, "total": 4, "rejected_edits": 0},
    ]
    done, = events(project, "implement.done")
    assert done.payload["passed"] is True and done.payload["iterations"] == 2
    assert done.payload["code_ref"] == res.code_ref

    calls = events(project, "llm.call")[-3:]
    assert [(c.zone, c.actor) for c in calls] == [
        ("clean", "clean.planner"), ("clean", "clean.executor"), ("clean", "clean.executor"),
    ]


def test_implement_cannot_take_dirty_ref(project, tmp_path):
    dirty = project.store.put_json(Zone.DIRTY, "release_package", "smuggled", {"spec": {}})
    gw, fake = make_gateway(project, [])
    sandbox = ScriptedSandbox(tmp_path / "ws", [])

    with pytest.raises(ZoneViolation):
        implement(project, dirty.id, gw, sandbox, ImplementConfig())

    assert fake.requests == []
    assert sandbox.cmds == []
    assert not (tmp_path / "ws").exists()


def test_done_flag_ignored_when_failing(quick_release, tmp_path):
    project, ref = quick_release
    failure = {"id": "S-002", "step": 1, "kind": "value", "pointer": "/error",
               "expected": "duplicate", "actual": "y" * 500}
    sandbox = ScriptedSandbox(tmp_path / "ws", [summary(2, 1, [failure]), summary(2, 2)])
    gw, fake = make_gateway(project, [
        turn(("main.py", BROKEN_MAIN), done=True),
        turn(("main.py", FAKE_CLONE)),
    ])

    res = implement(project, ref, gw, sandbox, ImplementConfig(max_iterations=5))

    assert res.passed and res.iterations == 2 and (res.passed_count, res.total) == (2, 2)
    first, second = executor_prompts(fake)
    assert not first.startswith(STILL_FAILING)
    assert second.startswith(STILL_FAILING)
    assert "passed 1/2" in second
    line = next(x for x in second.splitlines() if x.startswith("- S-002"))
    assert line.startswith("- S-002 step 1 value /error: expected 'duplicate', actual 'yyy")
    assert len(line) < 300  # value reprs are truncated to 120 chars


def test_done_without_claim_has_no_reminder(quick_release, tmp_path):
    project, ref = quick_release
    sandbox = ScriptedSandbox(tmp_path / "ws", [summary(2, 0), summary(2, 2)])
    gw, fake = make_gateway(project, [turn(("main.py", BROKEN_MAIN)), turn()])

    implement(project, ref, gw, sandbox, ImplementConfig(max_iterations=5))

    assert not any(p.startswith(STILL_FAILING) for p in executor_prompts(fake))


def test_oracle_command_and_files(quick_release, tmp_path):
    project, ref = quick_release
    ws = tmp_path / "ws"
    sandbox = ScriptedSandbox(ws, [summary(2, 2)])
    gw, _ = make_gateway(project, [turn(("main.py", FAKE_CLONE))])

    implement(project, ref, gw, sandbox,
              ImplementConfig(app_cmd="uvicorn main:app --log-level warning"))

    cmd, = sandbox.cmds
    assert cmd[:2] == ["python", "-I"]  # isolated mode: the workspace cannot shadow imports
    assert cmd[-6:-1] == ["oracle_runner.py", "oracle_scenarios.json", "--app",
                          "uvicorn main:app --log-level warning", "--port"]
    assert cmd[-1].isdigit()
    assert (ws / "oracle_runner.py").read_text(encoding="utf-8") == Path(
        inspect.getsourcefile(standalone)
    ).read_text(encoding="utf-8")
    scenarios = json.loads((ws / "oracle_scenarios.json").read_text(encoding="utf-8"))
    assert scenarios == project.store.get_json(ref, Zone.RELEASED)["scenarios"]
    assert [s["id"] for s in scenarios] == ["S-001", "S-002"]
    assert (ws / "requirements.txt").read_text(encoding="utf-8").split() == [
        "fastapi", "uvicorn", "httpx"
    ]


def test_template_is_minimal_fastapi_app(quick_release, tmp_path):
    project, ref = quick_release
    ws = tmp_path / "ws"
    gw, fake = make_gateway(project, [turn()])
    implement(project, ref, gw, ScriptedSandbox(ws, [summary(2, 2)]), ImplementConfig())
    template = (ws / "main.py").read_text(encoding="utf-8")
    assert "app = FastAPI()" in template
    assert "@app" not in template
    assert "=== main.py ===\n" + template in executor_prompts(fake)[0]


def test_existing_workspace_files_are_kept(quick_release, tmp_path):
    project, ref = quick_release
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "main.py").write_text(FAKE_CLONE, encoding="utf-8")
    gw, _ = make_gateway(project, [turn()])
    implement(project, ref, gw, ScriptedSandbox(ws, [summary(2, 2)]), ImplementConfig())
    assert (ws / "main.py").read_text(encoding="utf-8") == FAKE_CLONE


def test_oracle_files_cannot_be_edited(quick_release, tmp_path):
    project, ref = quick_release
    ws = tmp_path / "ws"
    sandbox = ScriptedSandbox(ws, [summary(2, 0), summary(2, 2)])
    gw, fake = make_gateway(project, [
        turn(("oracle_runner.py", "print('{\"total\": 2, \"passed\": 2, \"failed\": []}')"),
             ("oracle_scenarios.json", "[]")),
        turn(),
    ])

    implement(project, ref, gw, sandbox, ImplementConfig())

    second = executor_prompts(fake)[1]
    assert "Rejected edit oracle_runner.py: protected file" in second
    assert "Rejected edit oracle_scenarios.json: protected file" in second
    assert "passed" not in (ws / "oracle_runner.py").read_text(encoding="utf-8")[:200]
    assert json.loads((ws / "oracle_scenarios.json").read_text(encoding="utf-8")) != []


def test_runner_crash_feeds_back_output_tail(quick_release, tmp_path):
    project, ref = quick_release
    noise = "\n".join(f"log line {i}" for i in range(100))
    crash = RunResult(1, noise, "Traceback: ModuleNotFoundError: boom", False)
    sandbox = ScriptedSandbox(tmp_path / "ws", [crash, summary(2, 2)])
    gw, fake = make_gateway(project, [turn(("main.py", BROKEN_MAIN)), turn()])

    res = implement(project, ref, gw, sandbox, ImplementConfig())

    assert res.passed and res.iterations == 2
    second = executor_prompts(fake)[1]
    assert "passed 0/2" in second
    assert "ModuleNotFoundError: boom" in second
    assert "log line 99" in second and "log line 41" in second
    assert "log line 40\n" not in second  # only the last 60 lines are fed back
    first_iteration = events(project, "implement.iteration")[0].payload
    assert first_iteration["passed"] == 0 and first_iteration["total"] == 2


def test_stops_at_max_iterations(quick_release, tmp_path):
    project, ref = quick_release
    sandbox = ScriptedSandbox(tmp_path / "ws", [summary(2, 1), summary(2, 1)])
    gw, _ = make_gateway(project, [turn(), turn()])

    res = implement(project, ref, gw, sandbox, ImplementConfig(max_iterations=2))

    assert not res.passed
    assert (res.iterations, res.passed_count, res.total) == (2, 1, 2)
    assert res.code_ref is not None
    done, = events(project, "implement.done")
    assert done.payload["passed"] is False and done.payload["iterations"] == 2


def test_feedback_reaches_planner_and_executor(quick_release, tmp_path):
    project, ref = quick_release
    gw, fake = make_gateway(project, [turn()])
    feedback = ["Create task: step 1 POST /api/tasks: expected status 409"]
    implement(project, ref, gw, ScriptedSandbox(tmp_path / "ws", [summary(2, 2)]),
              ImplementConfig(feedback=feedback))
    for request in fake.requests:
        assert feedback[0] in request.messages[0].content


# --- final review fixes --------------------------------------------------------------------

SYNTAX_ERROR_MAIN = "from fastapi import FastAPI\napp = FastAPI(\n"


def test_crash_tail_reaches_the_prompt_without_paths_or_identity(quick_release):
    from reverseai.project import slug

    project, ref = quick_release
    ws = project.dir / "workspace"  # worst case: the workspace path names the project
    gw, fake = make_gateway(project, [turn(("main.py", SYNTAX_ERROR_MAIN)), turn()])

    implement(project, ref, gw, LocalSandbox(ws), ImplementConfig(max_iterations=2))

    second = executor_prompts(fake)[1]
    assert "app did not start" in second
    assert 'File "./main.py", line 2' in second  # scrubbed before the tail is shortened
    assert str(ws.resolve())[:15] not in second  # not even a cut-off absolute path
    assert slug(project.card.name) not in second


def test_test_summaries_are_scrubbed_before_the_prompt(quick_release, tmp_path):
    project, ref = quick_release
    ws = tmp_path / "ws"
    crash = RunResult(
        1, f'File "{ws}/main.py", line 2\nTaskBoard Pro at https://{TARGET_HOST}/api failed\n',
        "", False,
    )
    failed = [{"id": "S-001", "step": 0, "kind": "error", "pointer": None,
               "expected": "app did not start", "actual": f"{ws.resolve()}/main.py broke"}]
    sandbox = ScriptedSandbox(ws, [crash, summary(2, 0, failed), summary(2, 2)])
    gw, fake = make_gateway(project, [turn(), turn(), turn()])

    implement(project, ref, gw, sandbox, ImplementConfig(max_iterations=3))

    second, third = executor_prompts(fake)[1:]
    assert 'File "./main.py", line 2' in second
    assert "Tasklet at <original> failed" in second
    assert "./main.py broke" in third
    for prompt in (second, third):
        assert str(tmp_path) not in prompt and "TaskBoard" not in prompt
        assert TARGET_HOST not in prompt


def test_oracle_files_are_protected_whatever_the_letter_case(quick_release, tmp_path):
    project, ref = quick_release
    ws = tmp_path / "ws"
    sandbox = ScriptedSandbox(ws, [summary(2, 0), summary(2, 2)])
    gw, fake = make_gateway(project, [
        turn(("Oracle_Runner.py", "print('forged')"), ("ORACLE_SCENARIOS.JSON", "[]")),
        turn(),
    ])

    implement(project, ref, gw, sandbox, ImplementConfig())

    second = executor_prompts(fake)[1]
    assert "Rejected edit Oracle_Runner.py: protected file" in second
    assert "Rejected edit ORACLE_SCENARIOS.JSON: protected file" in second


def test_executor_output_error_still_records_implement_done(quick_release, tmp_path):
    from reverseai.llm.jsonout import LLMOutputError

    project, ref = quick_release
    sandbox = ScriptedSandbox(tmp_path / "ws", [])
    gw, _ = make_gateway(project, ["not json", "still not json"])

    with pytest.raises(LLMOutputError):
        implement(project, ref, gw, sandbox, ImplementConfig())

    done, = events(project, "implement.done")
    assert done.payload["passed"] is False
    assert done.payload["iterations"] == 1
    assert done.payload["error"].startswith("LLMOutputError")
