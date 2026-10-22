import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest

from reverseai import pipeline
from reverseai.barrier.release import Approval
from reverseai.bench.server import load_target, serve_asgi
from reverseai.config import ModelSpec, ProviderSpec, RoleSpec, Settings, load_settings
from reverseai.implement.agent import AgentTurn, FileEdit, ImplementResult
from reverseai.llm.gateway import Gateway
from reverseai.llm.providers import FakeProvider
from reverseai.llm.types import LLMRequest
from reverseai.observe.explorer import PageObservation
from reverseai.observe.har import Exchange
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step, StepFailure
from reverseai.parity.differential import ParityReport, ScenarioParity
from reverseai.pipeline import (
    Phase,
    PipelineState,
    build_gateway,
    load_state,
    record_observation,
    run_audit,
    run_build_loop,
    run_implement,
    run_observe,
    run_oracle,
    run_parity_phase,
    run_prepare_release,
    run_release,
    run_spec,
    save_state,
)
from reverseai.project import Attestation, Mode, Project, ProjectCard, create_project
from reverseai.sandbox import LocalSandbox, ServiceHandle
from reverseai.sandbox.base import free_port
from reverseai.zones.store import Zone

FIXTURES = Path(__file__).parent / "fixtures"
ANALYST_JSON = (FIXTURES / "llm" / "analyst_spec.json").read_text(encoding="utf-8")
CRITIC_JSON = (FIXTURES / "llm" / "critic.json").read_text(encoding="utf-8")
FAKE_CLONE = (FIXTURES / "fake_clone" / "main.py").read_text(encoding="utf-8")
PLAN = "1. Keep tasks in a dict.\n2. Validate in the documented order."

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
    ("POST", "/api/tasks", {"title": "x", "priority": "urgent"}),
]
PROBES: list[tuple[str, str, Any]] = [
    ("GET", "/api/tasks/999999", None),
    ("PATCH", "/api/tasks/999999", {"done": True}),
]


def make_card(**over) -> ProjectCard:
    base: dict = {
        "name": "Pipeline Demo",
        "mode": Mode.LEGACY,
        "target_base_url": "https://app.example.com/",
        "allowed_domains": ["app.example.com"],
        "target_is_sandbox": True,
        "attestation": Attestation(
            lawful_access=True, basis="own contract", signed_by="Ivan",
            signed_at="2026-10-20T10:00:00Z",
        ),
        "brand_terms": ["TaskBoard Pro"],
        "product_name": "Tasklet",
    }
    base.update(over)
    return ProjectCard(**base)


@pytest.fixture
def project(tmp_path) -> Project:
    return create_project(make_card(), tmp_path / "projects")


def by_role(**texts: str):
    def responder(req: LLMRequest) -> str:
        role = (req.system or "").split("]")[0].removeprefix("[role:")
        if role not in texts:
            raise AssertionError(f"unexpected role {role!r}")
        return texts[role]

    return responder


def fake_gateway(project: Project, **texts: str) -> tuple[Gateway, FakeProvider]:
    fake = FakeProvider(name="anthropic", responder=by_role(**texts))
    gateway = Gateway(
        load_settings(), {"anthropic": fake}, project.ledger,
        transcripts_dir=project.dir / "transcripts",
    )
    return gateway, fake


def record(client: httpx.Client, base_url: str, script, prefix: str) -> list[Exchange]:
    exchanges = []
    for i, (method, path, body) in enumerate(script):
        r = client.request(method, path, json=body)
        exchanges.append(
            Exchange(
                id=f"{prefix}{i}",
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


def page(url: str) -> PageObservation:
    return PageObservation(
        url=url, title="Board", links=[], forms=[], buttons=["Add"],
        text_excerpt="tasks", screenshot_ref=None,
    )


def completed(project: Project) -> list[Phase]:
    return load_state(project).completed


def phase_events(project: Project) -> list[str]:
    return [e.payload["phase"] for e in project.ledger.events() if e.type == "phase.completed"]


# --- state and phase order -----------------------------------------------------------------


def test_state_roundtrip_and_implicit_intake(project) -> None:
    raw = json.loads((project.dir / "state.json").read_text(encoding="utf-8"))
    assert raw == {"completed": [], "refs": {}, "parity_rounds": 0}

    state = load_state(project)
    assert state == PipelineState(completed=[Phase.INTAKE], refs={}, parity_rounds=0,
                                  workspace=None)

    state.refs["spec"] = "abc"
    state.parity_rounds = 2
    save_state(project, state)
    raw = json.loads((project.dir / "state.json").read_text(encoding="utf-8"))
    assert raw == {"completed": ["intake"], "refs": {"spec": "abc"}, "parity_rounds": 2,
                   "workspace": None}
    assert load_state(project) == state


def test_phase_values_are_lowercase() -> None:
    assert [p.value for p in Phase] == [
        "intake", "observe", "oracle", "spec", "prepare_release", "release",
        "implement", "parity", "audit",
    ]


def test_phase_order_enforced(project) -> None:
    with pytest.raises(RuntimeError, match="phase 'oracle' must be completed first"):
        run_spec(project, gateway=None)
    assert completed(project) == [Phase.INTAKE]
    assert phase_events(project) == []


@pytest.mark.parametrize(
    ("call", "missing"),
    [
        (lambda p, tmp: run_oracle(p), "observe"),
        (lambda p, tmp: run_spec(p, None), "oracle"),
        (lambda p, tmp: run_prepare_release(p), "spec"),
        (lambda p, tmp: run_release(p, None), "prepare_release"),
        (lambda p, tmp: run_implement(p, None, None), "release"),
        (lambda p, tmp: run_parity_phase(p, "http://127.0.0.1:1"), "implement"),
        (lambda p, tmp: run_build_loop(p, None, lambda: None), "release"),
        (lambda p, tmp: run_audit(p, tmp), "parity"),
    ],
)
def test_each_phase_requires_its_predecessor(project, tmp_path, call, missing) -> None:
    with pytest.raises(RuntimeError, match=f"phase '{missing}' must be completed first"):
        call(project, tmp_path / "out")


@pytest.mark.parametrize("option", ["submit_forms", "probe"])
def test_writing_observation_of_non_sandbox_target_is_refused(tmp_path, option) -> None:
    from reverseai.project import IntakeError

    project = create_project(make_card(target_is_sandbox=False), tmp_path / "projects")
    with pytest.raises(IntakeError, match="sandbox"):
        run_observe(project, **{option: True})
    assert completed(project) == [Phase.INTAKE]
    assert project.store.list() == []  # refused before any browsing


# --- observation storage ------------------------------------------------------------------


def test_record_observation_stores_dirty_artifacts(project) -> None:
    har_ex = Exchange(
        id="h0", method="POST", url="https://app.example.com/api/tasks", path="/api/tasks",
        query={}, status=201, request_json={"title": "a"}, response_json={"id": 1},
        response_content_type="application/json",
    )
    probe_ex = har_ex.model_copy(update={"id": "p0", "status": 422, "request_json": {},
                                         "response_json": {"error": "title_required"}})
    record_observation(
        project, pages=[page("https://app.example.com/")], har_exchanges=[har_ex],
        probe_exchanges=[probe_ex], har_ref="har-id",
    )

    state = load_state(project)
    assert state.completed == [Phase.INTAKE, Phase.OBSERVE]
    assert state.refs["har"] == "har-id"
    store = project.store
    for key, kind in [("exchanges", "exchanges"), ("probe_exchanges", "probe_exchanges"),
                      ("endpoints", "endpoints"), ("pages", "page_index")]:
        ref = store.ref(state.refs[key])
        assert (ref.zone, ref.kind) == (Zone.DIRTY, kind)
    exchanges = store.get_json(state.refs["exchanges"], Zone.DIRTY)
    assert [e["id"] for e in exchanges] == ["h0", "p0"]
    [endpoint] = store.get_json(state.refs["endpoints"], Zone.DIRTY)
    assert endpoint["statuses"] == [201, 422]
    [page_ref] = store.get_json(state.refs["pages"], Zone.DIRTY)
    assert store.get_json(page_ref, Zone.DIRTY)["url"] == "https://app.example.com/"
    assert phase_events(project) == ["intake", "observe"]


def test_rerunning_a_phase_overwrites_refs_without_duplicating(project) -> None:
    ex = Exchange(
        id="h0", method="GET", url="https://app.example.com/api/stats", path="/api/stats",
        query={}, status=200, request_json=None, response_json={"total": 0},
        response_content_type="application/json",
    )
    record_observation(project, pages=[], har_exchanges=[ex], probe_exchanges=[])
    first = load_state(project).refs["exchanges"]
    other = ex.model_copy(update={"id": "h1"})
    record_observation(project, pages=[], har_exchanges=[other], probe_exchanges=[])
    state = load_state(project)
    assert state.completed == [Phase.INTAKE, Phase.OBSERVE]
    assert state.refs["exchanges"] != first
    assert "har" not in state.refs


# --- oracle -> spec -> prepare-release -> release on the live taskboard ----------------------


@pytest.fixture
def taskboard_server():
    app = taskboard.create_app()
    with serve_asgi(app) as url:
        yield app, url


@pytest.fixture
def observed(tmp_path, taskboard_server) -> tuple[Project, Any]:
    """A project on the live taskboard whose observe-phase refs are recorded exchanges."""
    app, url = taskboard_server
    taskboard.reset_state(app)
    with httpx.Client(base_url=url, trust_env=False) as client:
        har_exchanges = record(client, url, SCRIPT, "h")
        probe_exchanges = record(client, url, PROBES, "p")
    taskboard.reset_state(app)
    card = make_card(target_base_url=url + "/", allowed_domains=["127.0.0.1"])
    project = create_project(card, tmp_path / "projects")
    record_observation(
        project, pages=[page(url + "/")], har_exchanges=har_exchanges,
        probe_exchanges=probe_exchanges,
    )
    return project, app


def test_oracle_spec_prepare_and_release(observed) -> None:
    project, _ = observed
    run_oracle(project)
    scenarios = project.store.get_json(load_state(project).refs["scenarios"], Zone.DIRTY)
    assert len(scenarios) >= 5
    assert any("→ 409" in s["title"] for s in scenarios)

    gateway, fake = fake_gateway(project, analyst=ANALYST_JSON, spec_critic='{"issues": []}')
    run_spec(project, gateway)
    spec_ref = project.store.ref(load_state(project).refs["spec"])
    assert (spec_ref.zone, spec_ref.kind) == (Zone.DIRTY, "spec")
    spec = project.store.get_json(spec_ref.id, Zone.DIRTY)
    assert spec["product_name"] == "Tasklet"
    assert {a["path"] for a in spec["api"]} >= {"/api/tasks", "/api/tasks/{id}"}
    analyst_prompt = fake.requests[0].messages[0].content
    assert "GET /api/tasks/999999 -> 404" in analyst_prompt  # probe exchanges reach the bundle
    assert "Board" in analyst_prompt  # the page index reaches the bundle

    run_prepare_release(project)
    state = load_state(project)
    draft = project.store.get_json(state.refs["release_draft"], Zone.DIRTY)
    sha = draft["package_sha256"]
    assert pipeline.draft_sha256(project) == sha
    markdown = pipeline.release_draft_path(project)
    assert markdown == project.dir / "release_draft.md"
    assert sha in markdown.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="phase 'release' must be completed first"):
        run_implement(project, gateway, None)

    approval = Approval(approver="Petrov", role="customer_analyst",
                        approved_at="2026-10-21T09:00:00Z", package_sha256=sha)
    run_release(project, approval)
    state = load_state(project)
    package_ref = project.store.ref(state.refs["release"])
    assert (package_ref.zone, package_ref.kind) == (Zone.RELEASED, "release_package")
    package = project.store.get_json(package_ref.id, Zone.CLEAN)
    assert package["approval"]["approver"] == "Petrov"
    assert len(package["scenarios"]) == len(scenarios)

    assert state.completed == [
        Phase.INTAKE, Phase.OBSERVE, Phase.ORACLE, Phase.SPEC, Phase.PREPARE_RELEASE,
        Phase.RELEASE,
    ]
    assert phase_events(project) == [
        "intake", "observe", "oracle", "spec", "prepare_release", "release",
    ]
    assert project.ledger.verify().ok


def test_release_with_wrong_sha_is_rejected(observed) -> None:
    from reverseai.barrier.release import ReleaseError

    project, _ = observed
    run_oracle(project)
    gateway, _ = fake_gateway(project, analyst=ANALYST_JSON, spec_critic=CRITIC_JSON)
    run_spec(project, gateway)
    run_prepare_release(project)
    approval = Approval(approver="Petrov", role="operator",
                        approved_at="2026-10-21T09:00:00Z", package_sha256="0" * 64)
    with pytest.raises(ReleaseError):
        run_release(project, approval)
    assert Phase.RELEASE not in completed(project)


def test_build_loop_parity_and_audit_on_live_taskboard(observed, tmp_path) -> None:
    project, app = observed
    run_oracle(project)
    turn = AgentTurn(notes="clone", edits=[FileEdit(path="main.py", content=FAKE_CLONE)],
                     done=True).model_dump_json()
    gateway, _ = fake_gateway(project, analyst=ANALYST_JSON, spec_critic='{"issues": []}',
                              planner=PLAN, executor=turn)
    run_spec(project, gateway)
    run_prepare_release(project)
    run_release(project, Approval(
        approver="Petrov", role="operator", approved_at="2026-10-21T09:00:00Z",
        package_sha256=pipeline.draft_sha256(project),
    ))

    workdir = project.dir / "workspace"
    report = run_build_loop(
        project, gateway, lambda: LocalSandbox(workdir),
        reset_original=lambda: taskboard.reset_state(app), delay_s=0.0,
    )
    assert report.total > 0
    assert report.ratio == 1.0 and report.critical_ratio == 1.0
    state = load_state(project)
    assert state.parity_rounds == 1
    assert project.store.ref(state.refs["parity_report"]).zone == Zone.VERIFIER
    assert project.store.ref(state.refs["code"]).zone == Zone.CLEAN

    audit = run_audit(project, tmp_path / "evidence")
    zip_path = audit.zip_path
    assert zip_path.is_file()
    assert audit.similarity.ok and audit.brand_hits == [] and audit.passed
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        similarity = json.loads(archive.read("similarity_report.json"))
    assert {"README.md", "parity_report.json", "similarity_report.json"} <= names
    assert "main.py" in similarity["per_file"]
    assert state.completed[-2:] == [Phase.IMPLEMENT, Phase.PARITY]
    assert completed(project)[-1] == Phase.AUDIT
    assert project.ledger.verify().ok
    clean_reads = [
        e.payload for e in project.ledger.events()
        if e.type == "artifact.read" and e.payload["reader"] == "clean"
    ]
    assert clean_reads and all(p["zone"] in ("clean", "released") for p in clean_reads)


# --- build loop wiring --------------------------------------------------------------------


class FakeSandbox:
    isolated = False

    def __init__(self, workdir: Path, log: list):
        self.workdir = workdir
        self.log = log

    def run(self, cmd, *, timeout=600):
        raise AssertionError("not used")

    def start(self, cmd, *, port, ready_path="/", timeout=30):
        self.log.append(("start", port, list(cmd)))
        return ServiceHandle(f"http://127.0.0.1:{port}", lambda: self.log.append(("stop", port)))


def _report(ok: bool) -> ParityReport:
    failure = StepFailure(step=0, kind="status", pointer=None, expected=409, actual=201)
    return ParityReport(
        total=1, passed=int(ok), critical_total=1, critical_passed=int(ok), unstable=[],
        results=[ScenarioParity(id="s001", title="POST /api/tasks → 409", critical=True,
                                original_ok=True, clone_ok=ok,
                                failures=[] if ok else [failure])],
    )


def _package(project: Project, scenarios: list[Scenario]) -> str:
    """A released package holding `scenarios` (no barrier run), for build-loop wiring tests."""
    return project.store.put_json(
        Zone.RELEASED, "release_package", "release:test",
        {"scenarios": [s.model_dump(mode="json") for s in scenarios]},
    ).id


def test_build_loop_feeds_parity_failures_back(project, monkeypatch) -> None:
    scenario = Scenario(id="s001", title="POST /api/tasks → 409", critical=True, steps=[
        ScenarioStep(step=Step(method="POST", path="/api/tasks", json_body={"title": "a"}),
                     expect=Expect(status=409)),
    ])
    state = load_state(project)
    state.refs["scenarios"] = project.store.put_json(
        Zone.DIRTY, "scenarios", "scenarios", [scenario.model_dump(mode="json")]).id
    state.refs["release"] = _package(project, [scenario])
    state.completed += [Phase.OBSERVE, Phase.ORACLE, Phase.SPEC, Phase.PREPARE_RELEASE,
                        Phase.RELEASE]
    save_state(project, state)

    log: list = []
    feedbacks: list[list[str]] = []
    reports = [_report(False), _report(True)]

    def fake_implement(project_, gateway, sandbox, *, feedback=()):
        feedbacks.append(list(feedback))
        return ImplementResult(iterations=1, passed=True, total=1, passed_count=1,
                               workspace=sandbox.workdir)

    def fake_parity(project_, clone_url, *, reset_original=None, reset_clone=None, **kw):
        log.append(("parity", clone_url))
        reset_clone()
        return reports.pop(0)

    monkeypatch.setattr(pipeline, "run_implement", fake_implement)
    monkeypatch.setattr(pipeline, "run_parity_phase", fake_parity)
    sandboxes: list[FakeSandbox] = []

    def factory() -> FakeSandbox:
        sandboxes.append(FakeSandbox(project.dir / "workspace", log))
        return sandboxes[-1]

    report = run_build_loop(project, None, factory, max_rounds=3)

    assert report.ratio == 1.0
    assert len(sandboxes) == 2
    assert feedbacks[0] == []
    assert feedbacks[1] == [
        "POST /api/tasks → 409: step 1 POST /api/tasks: expected status = 409"
    ]
    assert load_state(project).parity_rounds == 2
    # each round: start, parity, restart on the same port (stop + start), final stop
    first_port = log[0][1]
    assert log[0][2] == ["python", "-m", "uvicorn", "main:app", "--port", str(first_port),
                         "--host", "127.0.0.1"]
    assert [entry[0] for entry in log] == ["start", "parity", "stop", "start", "stop"] * 2
    assert log[1] == ("parity", f"http://127.0.0.1:{first_port}")
    assert {entry[1] for entry in log[:5] if entry[0] != "parity"} == {first_port}


def test_build_loop_stops_after_max_rounds(project, monkeypatch) -> None:
    state = load_state(project)
    state.refs["scenarios"] = project.store.put_json(Zone.DIRTY, "scenarios", "s", []).id
    state.refs["release"] = _package(project, [])
    state.completed += [Phase.OBSERVE, Phase.ORACLE, Phase.SPEC, Phase.PREPARE_RELEASE,
                        Phase.RELEASE]
    save_state(project, state)
    calls: list[int] = []
    monkeypatch.setattr(pipeline, "run_implement", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(pipeline, "run_parity_phase", lambda *a, **k: _report(False))
    report = run_build_loop(
        project, None, lambda: FakeSandbox(project.dir / "w", []), max_rounds=2
    )
    assert report.ratio == 0.0
    assert len(calls) == 2
    assert load_state(project).parity_rounds == 2


# --- gateway ------------------------------------------------------------------------------


def test_build_gateway_uses_project_ledger_and_transcripts(project) -> None:
    settings = Settings(
        providers={"local": ProviderSpec(kind="fake", jurisdiction="self")},
        models={"m": ModelSpec(provider="local", input_per_mtok=0, output_per_mtok=0)},
        roles={"analyst": RoleSpec(candidates=["m"])},
    )
    gateway = build_gateway(project, settings, env={})
    assert gateway._transcripts_dir == project.dir / "transcripts"
    assert gateway._ledger is project.ledger
    assert set(gateway._providers) == {"local"}

    default = build_gateway(project, env={"ANTHROPIC_API_KEY": "k"})
    assert set(default._providers) == {"anthropic"}


# --- fix round 1 --------------------------------------------------------------------------


def test_intake_completion_is_recorded_once(project) -> None:
    save_state(project, load_state(project))
    save_state(project, load_state(project))
    assert phase_events(project) == ["intake"]


def _seed_spec(project: Project, scenarios: list[Scenario]) -> None:
    from reverseai.spec.model import AnalystDraft, BehaviorSpec

    draft = AnalystDraft.model_validate_json(ANALYST_JSON)
    spec = BehaviorSpec(product_name="Tasklet", api=[], **draft.model_dump())
    state = load_state(project)
    state.refs["spec"] = project.store.put_json(
        Zone.DIRTY, "spec", "spec", spec.model_dump(mode="json")).id
    state.refs["scenarios"] = project.store.put_json(
        Zone.DIRTY, "scenarios", "scenarios", [s.model_dump(mode="json") for s in scenarios]).id
    for phase in (Phase.OBSERVE, Phase.ORACLE, Phase.SPEC):
        if phase not in state.completed:
            state.completed.append(phase)
    save_state(project, state)


def _create(title: str) -> Scenario:
    return Scenario(id="s001", title="Create", critical=True, steps=[
        ScenarioStep(step=Step(method="POST", path="/api/tasks", json_body={"title": title}),
                     expect=Expect(status=201)),
    ])


@pytest.mark.usefixtures("lang_ru")  # checks the Russian copy
def test_prepare_release_rerun_with_same_spec_and_new_scenarios(project) -> None:
    _seed_spec(project, [_create("Milk")])
    run_prepare_release(project)
    first = load_state(project).refs["release_draft_md"]
    assert "Сценариев: 1" in pipeline.release_draft_path(project).read_text(encoding="utf-8")

    _seed_spec(project, [_create("Milk"), _create("Bread").model_copy(update={"id": "s002"})])
    run_prepare_release(project)
    state = load_state(project)
    assert state.refs["release_draft_md"] != first
    markdown = pipeline.release_draft_path(project).read_text(encoding="utf-8")
    assert "Сценариев: 2" in markdown
    assert markdown.encode("utf-8") == project.store.get(state.refs["release_draft_md"],
                                                         Zone.DIRTY)
    draft = project.store.get_json(state.refs["release_draft"], Zone.DIRTY)
    assert len(draft["scenarios"]) == 2


class FlakySandbox(FakeSandbox):
    """Fails to start the clone the first `failures` times."""

    def __init__(self, workdir: Path, log: list, failures: list[int]):
        super().__init__(workdir, log)
        self.failures = failures

    def start(self, cmd, *, port, ready_path="/", timeout=30):
        if self.failures[0] > 0:
            self.failures[0] -= 1
            self.log.append(("failed-start", port))
            raise TimeoutError("service at http://127.0.0.1 not ready after 30s:\nboom")
        return super().start(cmd, port=port)


def _released_state(project: Project) -> None:
    state = load_state(project)
    state.refs["scenarios"] = project.store.put_json(Zone.DIRTY, "scenarios", "s", []).id
    state.refs["release"] = _package(project, [])
    state.completed += [Phase.OBSERVE, Phase.ORACLE, Phase.SPEC, Phase.PREPARE_RELEASE,
                        Phase.RELEASE]
    save_state(project, state)


def test_build_loop_counts_a_clone_that_does_not_start_as_a_failed_round(
    project, monkeypatch
) -> None:
    _released_state(project)
    log: list = []
    feedbacks: list[list[str]] = []
    failures = [1]

    def fake_implement(project_, gateway, sandbox, *, feedback=()):
        feedbacks.append(list(feedback))

    monkeypatch.setattr(pipeline, "run_implement", fake_implement)
    monkeypatch.setattr(pipeline, "run_parity_phase", lambda *a, **k: _report(True))
    report = run_build_loop(
        project, None, lambda: FlakySandbox(project.dir / "w", log, failures), max_rounds=3
    )

    assert report.ratio == 1.0
    assert [entry[0] for entry in log] == ["failed-start", "start", "stop"]
    assert feedbacks[0] == []
    assert feedbacks[1] == [pipeline.CLONE_DID_NOT_START]
    assert "boom" not in feedbacks[1][0]
    assert load_state(project).parity_rounds == 2
    rounds = [e.payload for e in project.ledger.events() if e.type == "pipeline.build_round"]
    assert [r["service_started"] for r in rounds] == [False, True]
    assert [r["meets_threshold"] for r in rounds] == [False, True]


def test_build_loop_raises_when_the_clone_never_starts(project, monkeypatch) -> None:
    _released_state(project)
    monkeypatch.setattr(pipeline, "run_implement", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "run_parity_phase", lambda *a, **k: _report(True))
    with pytest.raises(RuntimeError, match="did not start"):
        run_build_loop(
            project, None, lambda: FlakySandbox(project.dir / "w", [], [5]), max_rounds=2
        )
    assert load_state(project).parity_rounds == 2


# --- observe options ----------------------------------------------------------------------


def test_run_observe_passes_delay_to_explorer_and_probe(project, monkeypatch) -> None:
    from reverseai.observe.explorer import ExplorationResult

    seen: dict[str, Any] = {}

    def fake_explore(config, card, store):
        seen["explore"] = config.delay_s
        har = store.put_json(Zone.DIRTY, "har", "har", {"log": {"entries": []}})
        return ExplorationResult(pages=[], har_ref=har.id, expression_refs=[])

    def fake_probe(base_url, endpoints, card, *, delay_s, exchanges, ledger):
        seen["probe"] = delay_s
        return []

    monkeypatch.setattr(pipeline, "explore", fake_explore)
    monkeypatch.setattr(pipeline, "probe_endpoints", fake_probe)
    run_observe(project, probe=True, delay_s=0.05)
    assert seen == {"explore": 0.05, "probe": 0.05}

    run_observe(project, probe=True)
    assert seen == {"explore": 0.5, "probe": 0.5}  # ExplorerConfig's default rate limit


# --- fix round 1 (R15): oracle drops scenarios the original does not reproduce --------------


@pytest.fixture
def observed_with_hidden_state(tmp_path, taskboard_server) -> tuple[Project, Any]:
    """The 409 below was recorded against a task created before recording started."""
    app, url = taskboard_server
    taskboard.reset_state(app)
    with httpx.Client(base_url=url, trust_env=False) as client:
        client.post("/api/tasks", json={"title": "made before recording"})
        har_exchanges = record(client, url, [
            ("POST", "/api/tasks", {"title": "made before recording"}),  # 409 duplicate
            ("POST", "/api/tasks", {"title": ""}),  # 422, reproducible
        ], "h")
    assert [e.status for e in har_exchanges] == [409, 422]
    taskboard.reset_state(app)
    card = make_card(target_base_url=url + "/", allowed_domains=["127.0.0.1"])
    project = create_project(card, tmp_path / "projects")
    record_observation(project, pages=[], har_exchanges=har_exchanges, probe_exchanges=[])
    return project, app


def _scenario_titles(project: Project) -> list[str]:
    ref = load_state(project).refs["scenarios"]
    return [s["title"] for s in project.store.get_json(ref, Zone.DIRTY)]


def test_oracle_with_reset_drops_and_logs_unreproducible_scenarios(
    observed_with_hidden_state,
) -> None:
    project, app = observed_with_hidden_state
    run_oracle(project, reset_original=lambda: taskboard.reset_state(app))

    titles = _scenario_titles(project)
    assert not any("→ 409" in t for t in titles)
    assert any("→ 422" in t for t in titles)
    [event] = [e for e in project.ledger.events() if e.type == "oracle.unstable"]
    assert (event.zone, event.actor) == ("dirty", "oracle")
    assert len(event.payload["dropped"]) == 1
    assert event.payload["kept"] == len(titles)
    state = load_state(project)
    ref = project.store.ref(state.refs["oracle_unstable"])
    assert (ref.zone, ref.kind) == (Zone.DIRTY, "oracle_unstable")
    assert project.store.get_json(ref.id, Zone.DIRTY) == event.payload["dropped"]
    assert Phase.ORACLE in state.completed


def test_oracle_without_reset_keeps_every_scenario(observed_with_hidden_state) -> None:
    project, _ = observed_with_hidden_state
    run_oracle(project)
    titles = _scenario_titles(project)
    assert any("→ 409" in t for t in titles)
    assert not [e for e in project.ledger.events() if e.type == "oracle.unstable"]
    assert "oracle_unstable" not in load_state(project).refs


# --- fix round 2: the R15 filter has a floor ------------------------------------------------


def test_oracle_refuses_when_no_scenario_reproduces(tmp_path, taskboard_server) -> None:
    app, url = taskboard_server
    taskboard.reset_state(app)
    with httpx.Client(base_url=url, trust_env=False) as client:
        exchanges = record(client, url, SCRIPT, "h")
    dead = f"http://127.0.0.1:{free_port()}"  # the original is down during the replay
    project = create_project(
        make_card(target_base_url=dead + "/", allowed_domains=["127.0.0.1"]),
        tmp_path / "projects",
    )
    record_observation(project, pages=[], har_exchanges=exchanges, probe_exchanges=[])

    with pytest.raises(RuntimeError, match="no scenario reproduced"):
        run_oracle(project, reset_original=lambda: None)
    assert Phase.ORACLE not in completed(project)
    [event] = [e for e in project.ledger.events() if e.type == "oracle.unstable"]
    assert event.payload["kept"] == 0 and event.payload["dropped"]


def test_oracle_refuses_when_every_critical_scenario_is_dropped(observed) -> None:
    project, app = observed
    url = project.card.target_base_url.rstrip("/")

    def reset_that_breaks_the_original() -> None:
        taskboard.reset_state(app)
        httpx.post(url + "/api/tasks", json={"title": "write report"}, trust_env=False)

    with pytest.raises(RuntimeError, match="critical"):
        run_oracle(project, reset_original=reset_that_breaks_the_original)
    assert Phase.ORACLE not in completed(project)
    [event] = [e for e in project.ledger.events() if e.type == "oracle.unstable"]
    assert event.payload["kept"] > 0  # validation scenarios still reproduce


def test_oracle_with_reset_requires_a_sandbox_target(tmp_path) -> None:
    from reverseai.project import IntakeError

    project = create_project(make_card(target_is_sandbox=False), tmp_path / "projects")
    record_observation(project, pages=[], har_exchanges=[], probe_exchanges=[])
    with pytest.raises(IntakeError, match="sandbox"):
        run_oracle(project, reset_original=lambda: None)
    assert Phase.ORACLE not in completed(project)


# --- final review fixes --------------------------------------------------------------------


def _release_observed(project: Project) -> None:
    """oracle → spec → prepare-release → release with a fake gateway."""
    run_oracle(project)
    gateway, _ = fake_gateway(project, analyst=ANALYST_JSON, spec_critic='{"issues": []}')
    run_spec(project, gateway)
    run_prepare_release(project)
    run_release(project, Approval(
        approver="Petrov", role="operator", approved_at="2026-10-21T09:00:00Z",
        package_sha256=pipeline.draft_sha256(project),
    ))


def test_rerunning_a_phase_invalidates_every_later_phase(observed) -> None:
    from reverseai.pipeline import PhaseOrderError

    project, _ = observed
    _release_observed(project)
    state = load_state(project)
    state.completed.append(Phase.IMPLEMENT)
    state.refs["code"] = "code-id"
    save_state(project, state)

    assert pipeline.release_draft_path(project).exists()

    run_oracle(project)  # the scenarios changed: spec, release and code are stale now

    assert not pipeline.release_draft_path(project).exists()  # no stale draft to sign
    state = load_state(project)
    assert state.completed == [Phase.INTAKE, Phase.OBSERVE, Phase.ORACLE]
    for key in ("spec", "release_draft", "release_draft_md", "release", "code"):
        assert key not in state.refs
    assert {"scenarios", "exchanges", "endpoints"} <= set(state.refs)
    [event] = [e for e in project.ledger.events() if e.type == "phase.invalidated"]
    assert event.payload == {
        "phase": "oracle",
        "invalidated": ["spec", "prepare_release", "release", "implement"],
    }
    with pytest.raises(PhaseOrderError, match="phase 'release' must be completed first"):
        run_build_loop(project, None, lambda: None)


def test_rerunning_the_last_phase_invalidates_nothing(project) -> None:
    record_observation(project, pages=[], har_exchanges=[], probe_exchanges=[])
    record_observation(project, pages=[], har_exchanges=[], probe_exchanges=[])
    assert not [e for e in project.ledger.events() if e.type == "phase.invalidated"]


def test_parity_phase_checks_the_clone_against_the_released_scenarios(observed,
                                                                       monkeypatch) -> None:
    project, _ = observed
    _release_observed(project)
    state = load_state(project)
    state.completed.append(Phase.IMPLEMENT)
    save_state(project, state)
    seen: dict[str, Any] = {}

    def fake_run_parity(scenarios, original_url, clone_url, **kwargs):
        seen.update(kwargs, scenarios=scenarios)
        return ParityReport(total=0, passed=0, critical_total=0, critical_passed=0,
                            unstable=[], results=[])

    monkeypatch.setattr(pipeline, "run_parity", fake_run_parity)
    run_parity_phase(project, "http://127.0.0.1:1")
    package = project.store.get_json(load_state(project).refs["release"], Zone.VERIFIER)
    assert [s.model_dump(mode="json") for s in seen["released"]] == package["scenarios"]
    dirty = project.store.get_json(load_state(project).refs["scenarios"], Zone.DIRTY)
    assert [s.model_dump(mode="json") for s in seen["scenarios"]] == dirty


@pytest.mark.parametrize("sandbox", [True, False])
def test_parity_phase_is_throttled_and_read_only_on_a_non_sandbox(
    tmp_path, sandbox, monkeypatch
) -> None:
    project = create_project(make_card(target_is_sandbox=sandbox), tmp_path / "projects")
    state = load_state(project)
    state.refs["scenarios"] = project.store.put_json(Zone.DIRTY, "scenarios", "s", []).id
    state.refs["release"] = _package(project, [])
    state.completed += [Phase.OBSERVE, Phase.ORACLE, Phase.SPEC, Phase.PREPARE_RELEASE,
                        Phase.RELEASE, Phase.IMPLEMENT]
    save_state(project, state)
    seen: dict[str, Any] = {}

    def fake_run_parity(scenarios, original_url, clone_url, **kwargs):
        seen.update(kwargs)
        return ParityReport(total=0, passed=0, critical_total=0, critical_passed=0,
                            unstable=[], results=[])

    monkeypatch.setattr(pipeline, "run_parity", fake_run_parity)
    run_parity_phase(project, "http://127.0.0.1:1")
    assert seen["read_only_original"] is (not sandbox)
    assert seen["original_delay_s"] == 0.5  # default rate limit: at most 2 requests/second
    run_parity_phase(project, "http://127.0.0.1:1", delay_s=0.1)
    assert seen["original_delay_s"] == 0.1


def test_workspace_lives_outside_the_project_under_a_neutral_name(project) -> None:
    from reverseai.project import slug

    ws = pipeline.workspace_dir(project)
    assert ws.parent == project.dir.parent / ".workspaces"
    assert ws.is_dir()
    assert slug(project.card.name) not in str(ws)
    assert project.dir not in ws.parents
    assert len(ws.name) == 16 and int(ws.name, 16) >= 0
    assert load_state(project).workspace == str(ws)
    assert pipeline.workspace_dir(project) == ws  # stable across calls


def test_complete_rechecks_the_prerequisite(project) -> None:
    """A phase whose predecessor was invalidated meanwhile is not recorded as completed."""
    from reverseai.pipeline import PhaseOrderError

    save_state(project, load_state(project))
    with pytest.raises(PhaseOrderError):
        pipeline._complete(project, Phase.ORACLE, {"scenarios": "x"})
    assert Phase.ORACLE not in load_state(project).completed
