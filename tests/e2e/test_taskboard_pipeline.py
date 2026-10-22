"""The whole pipeline on the bundled taskboard: real browser, scripted LLM, hidden tests."""

import json
import os
from pathlib import Path

import pytest

from reverseai.bench.runner import (
    EVIDENCE_DIR,
    PROJECTS_DIR,
    RESULT_FILE,
    BenchResult,
    run_benchmark,
)
from reverseai.config import load_settings
from reverseai.implement.agent import AgentTurn, FileEdit
from reverseai.llm.gateway import Gateway
from reverseai.llm.providers import FakeProvider
from reverseai.llm.types import LLMRequest
from reverseai.pipeline import Phase, build_gateway, load_state
from reverseai.project import Project
from reverseai.sandbox import LocalSandbox
from reverseai.zones.store import Zone

FIXTURES = Path(__file__).parent.parent / "fixtures"
TEXTS = {
    "analyst": (FIXTURES / "llm" / "analyst_spec.json").read_text(encoding="utf-8"),
    "spec_critic": (FIXTURES / "llm" / "critic.json").read_text(encoding="utf-8"),
    "planner": (FIXTURES / "llm" / "planner.txt").read_text(encoding="utf-8"),
    "executor": AgentTurn(
        notes="clone written from the released spec",
        edits=[FileEdit(path="main.py",
                        content=(FIXTURES / "fake_clone" / "main.py").read_text(encoding="utf-8"))],
        done=True,
    ).model_dump_json(),
}


def respond_by_role(req: LLMRequest) -> str:
    role = (req.system or "").split("]")[0].removeprefix("[role:")
    if role not in TEXTS:
        raise AssertionError(f"unexpected role {role!r}")
    return TEXTS[role]


def scripted_gateway(project: Project) -> Gateway:
    return Gateway(
        load_settings(),
        {"anthropic": FakeProvider(name="anthropic", responder=respond_by_role)},
        project.ledger,
        transcripts_dir=project.dir / "transcripts",
    )


@pytest.mark.browser
def test_offline_benchmark_on_taskboard(tmp_path) -> None:
    workdir = tmp_path / "bench"
    result = run_benchmark(
        "taskboard", gateway=scripted_gateway, workdir=workdir, sandbox_factory=LocalSandbox
    )

    assert result.target == "taskboard"
    assert result.parity_ratio >= 0.95
    assert result.critical_ratio == 1.0
    assert result.hidden_total > 0
    assert result.hidden_passed == result.hidden_total
    assert result.similarity_max < 0.05
    assert result.cost_usd > 0
    assert result.duration_s > 0
    saved = json.loads((workdir / RESULT_FILE).read_text(encoding="utf-8"))
    assert BenchResult.model_validate(saved) == result

    [project_dir] = [d for d in (workdir / PROJECTS_DIR).iterdir() if d.name != ".workspaces"]
    project = Project.load(project_dir)
    workspace = Path(load_state(project).workspace)
    assert workspace.parent == workdir / PROJECTS_DIR / ".workspaces"  # outside the project
    assert (workspace / "main.py").is_file()
    assert project.card.target_is_sandbox
    assert load_state(project).completed == list(Phase)
    assert project.ledger.verify().ok
    assert list((workdir / EVIDENCE_DIR).glob("evidence_*.zip"))

    events = project.ledger.events()
    [auto] = [e for e in events if e.type == "bench.auto_approved"]
    assert auto.payload["auto_approved"] is True
    [released] = [e for e in events if e.type == "barrier.release"]
    assert released.seq > auto.seq
    calls = [e.payload for e in events if e.type == "llm.call"]
    assert {c["role"] for c in calls} >= {"analyst", "spec_critic", "planner", "executor"}
    assert result.cost_usd == pytest.approx(sum(c["cost_usd"] for c in calls))

    observed = {e.payload["kind"] for e in events
                if e.type == "artifact.put" and e.payload["zone"] == "dirty"}
    assert "expression" in observed  # the browser stored the original's JS
    probes = project.store.get_json(load_state(project).refs["probe_exchanges"], Zone.VERIFIER)
    assert probes  # probing ran against the sandbox target

    [unstable] = [e.payload for e in events if e.type == "oracle.unstable"]
    package = project.store.get_json(load_state(project).refs["release"], Zone.VERIFIER)
    assert len(package["scenarios"]) == unstable["kept"] == result.scenarios > 0
    # the explorer clicked the row controls: toggle and delete are released critical scenarios
    critical_writes = {
        (step["step"]["method"], step["expect"]["status"])
        for scenario in package["scenarios"] if scenario["critical"]
        for step in scenario["steps"]
    }
    assert {("PATCH", 200), ("DELETE", 204)} <= critical_writes
    [explored] = [e.payload for e in events if e.type == "observe.explore"]
    assert explored["clicks"] > 0 and explored["destructive_clicks"]

    iterations = [e.payload for e in events if e.type == "implement.iteration"]
    assert len(iterations) <= 3  # the released scenarios are all reproducible
    assert iterations[-1]["passed"] == iterations[-1]["total"] == unstable["kept"]

    clean_reads = [e.payload for e in events
                   if e.type == "artifact.read" and e.payload["reader"] == "clean"]
    assert clean_reads
    assert all(p["zone"] in ("clean", "released") for p in clean_reads)
    assert not [e for e in events if e.type == "zone.violation"]


@pytest.mark.live
@pytest.mark.browser
def test_live_benchmark_on_taskboard(tmp_path) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY is not set")
    result = run_benchmark(
        "taskboard", gateway=build_gateway, workdir=tmp_path / "bench",
        sandbox_factory=LocalSandbox,
    )
    assert isinstance(result, BenchResult)
