from datetime import datetime
from pathlib import Path

import pytest
import yaml
from playwright.sync_api import Error as PlaywrightError
from typer.testing import CliRunner

from reverseai import pipeline
from reverseai.cli import app
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.parity.differential import ParityReport
from reverseai.pipeline import Phase, load_state, save_state
from reverseai.project import Project
from reverseai.spec.model import AnalystDraft, BehaviorSpec
from reverseai.zones.store import Zone

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


FIXTURES = Path(__file__).parent / "fixtures"

CARD = {
    "name": "CLI Demo",
    "mode": "legacy",
    "target_base_url": "https://app.example.com/",
    "allowed_domains": ["app.example.com"],
    "attestation": {
        "lawful_access": True,
        "basis": "own contract",
        "signed_by": "Ivan",
        "signed_at": "2026-10-20T10:00:00Z",
    },
    "brand_terms": ["TaskBoard Pro"],
    "product_name": "Tasklet",
}

runner = CliRunner()


def invoke(*args: str):
    return runner.invoke(app, [str(a) for a in args])


def write_card(tmp_path: Path, **over) -> Path:
    path = tmp_path / "card.yaml"
    path.write_text(yaml.safe_dump({**CARD, **over}, allow_unicode=True), encoding="utf-8")
    return path


def init_project(tmp_path: Path, **over) -> Path:
    result = invoke("init", "--card", write_card(tmp_path, **over),
                    "--projects-root", tmp_path / "projects")
    assert result.exit_code == 0, result.output
    return tmp_path / "projects" / "cli-demo"


def test_cli_status_and_ledger_verify(tmp_path) -> None:
    result = invoke("init", "--card", write_card(tmp_path),
                    "--projects-root", tmp_path / "projects")
    assert result.exit_code == 0, result.output
    project_dir = tmp_path / "projects" / "cli-demo"
    assert str(project_dir) in result.output
    assert (project_dir / "card.json").is_file()
    project = Project.load(project_dir)
    assert load_state(project).completed == [Phase.INTAKE]
    intake_events = [e.payload["phase"] for e in project.ledger.events()
                     if e.type == "phase.completed"]
    assert intake_events == ["intake"]

    result = invoke("status", "--project", project_dir)
    assert result.exit_code == 0, result.output
    assert "intake" in result.output
    assert "Приём проекта" in result.output

    result = invoke("ledger-verify", "--project", project_dir)
    assert result.exit_code == 0, result.output
    assert "Журнал цел: цепочка хэшей не нарушена, событий:" in result.output
    assert "ok" not in result.output


def test_init_accepts_unquoted_yaml_timestamp(tmp_path) -> None:
    path = tmp_path / "card.yaml"
    text = yaml.safe_dump(CARD).replace("'2026-10-20T10:00:00Z'", "2026-10-20T10:00:00Z")
    path.write_text(text, encoding="utf-8")
    assert isinstance(yaml.safe_load(text)["attestation"]["signed_at"], datetime)
    result = invoke("init", "--card", path, "--projects-root", tmp_path / "projects")
    assert result.exit_code == 0, result.output
    card = Project.load(tmp_path / "projects" / "cli-demo").card
    assert card.attestation.signed_at.startswith("2026-10-20")


def test_init_rejects_card_without_attestation(tmp_path) -> None:
    attestation = {**CARD["attestation"], "lawful_access": False}
    result = invoke("init", "--card", write_card(tmp_path, attestation=attestation),
                    "--projects-root", tmp_path / "projects")
    assert result.exit_code == 1
    assert "Ошибка" in result.output
    assert "Traceback" not in result.output
    assert not (tmp_path / "projects" / "cli-demo").exists()


def test_init_rejects_invalid_card(tmp_path) -> None:
    path = tmp_path / "card.yaml"
    path.write_text("name: x\n", encoding="utf-8")
    result = invoke("init", "--card", path, "--projects-root", tmp_path / "projects")
    assert result.exit_code == 1
    assert "Ошибка" in result.output


def test_phase_order_error_is_reported_in_russian(tmp_path) -> None:
    project_dir = init_project(tmp_path)
    result = invoke("oracle", "--project", project_dir)
    assert result.exit_code == 1
    assert "Ошибка" in result.output and "observe" in result.output
    assert "Traceback" not in result.output


def test_missing_project_is_reported(tmp_path) -> None:
    result = invoke("status", "--project", tmp_path / "nope")
    assert result.exit_code == 1
    assert "Ошибка" in result.output


def test_ledger_verify_reports_tampering(tmp_path) -> None:
    project_dir = init_project(tmp_path)
    ledger = project_dir / "ledger.jsonl"
    ledger.write_text(ledger.read_text(encoding="utf-8").replace("CLI Demo", "CLI Dem0"),
                      encoding="utf-8")
    result = invoke("ledger-verify", "--project", project_dir)
    assert result.exit_code == 1
    assert "нарушена" in result.output
    assert "Ошибка" not in result.output


def test_costs_summarizes_llm_calls_from_ledger(tmp_path) -> None:
    project_dir = init_project(tmp_path)
    project = Project.load(project_dir)
    for role, model, cost in [("analyst", "m-1", 0.5), ("analyst", "m-1", 0.25),
                              ("executor", "m-2", 1.0)]:
        project.ledger.append("llm.call", "dirty", role, {
            "role": role, "model": model, "provider": "p", "usage": {}, "cost_usd": cost,
        })
    result = invoke("costs", "--project", project_dir)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert "Вызовов LLM: 3" in lines
    assert "Стоимость, USD: 1.7500" in lines
    assert "  analyst: вызовов 2, 0.7500 USD" in lines
    assert "  m-2 (p): вызовов 1, 1.0000 USD" in lines


def _spec_ready(project_dir: Path) -> None:
    project = Project.load(project_dir)
    draft = AnalystDraft.model_validate_json(
        (FIXTURES / "llm" / "analyst_spec.json").read_text(encoding="utf-8")
    )
    spec = BehaviorSpec(product_name="Tasklet", api=[], **draft.model_dump())
    scenario = Scenario(id="s001", title="Create a task", critical=True, steps=[
        ScenarioStep(step=Step(method="POST", path="/api/tasks", json_body={"title": "Milk"}),
                     expect=Expect(status=201, json_equals={"/title": "Milk"})),
    ])
    state = load_state(project)
    state.refs["spec"] = project.store.put_json(
        Zone.DIRTY, "spec", "spec", spec.model_dump(mode="json")).id
    state.refs["scenarios"] = project.store.put_json(
        Zone.DIRTY, "scenarios", "scenarios", [scenario.model_dump(mode="json")]).id
    state.completed += [Phase.OBSERVE, Phase.ORACLE, Phase.SPEC]
    save_state(project, state)


def test_prepare_release_and_approve(tmp_path) -> None:
    project_dir = init_project(tmp_path)
    _spec_ready(project_dir)

    result = invoke("prepare-release", "--project", project_dir)
    assert result.exit_code == 0, result.output
    project = Project.load(project_dir)
    draft = project.store.get_json(load_state(project).refs["release_draft"], Zone.DIRTY)
    sha = draft["package_sha256"]
    assert f"SHA-256 пакета (спецификация + сценарии): {sha}" in result.output
    assert draft["spec_sha256"] not in result.output
    assert str(project_dir / "release_draft.md") in result.output

    result = invoke("approve", "--project", project_dir, "--approver", "Petrov",
                    "--role", "customer_analyst", "--sha", "0" * 64)
    assert result.exit_code == 1
    assert "Ошибка" in result.output and "Traceback" not in result.output

    result = invoke("approve", "--project", project_dir, "--approver", "Petrov",
                    "--role", "customer_analyst", "--sha", sha)
    assert result.exit_code == 0, result.output
    state = load_state(Project.load(project_dir))
    assert state.completed[-1] == Phase.RELEASE
    approved = [e for e in Project.load(project_dir).ledger.events()
                if e.type == "barrier.approved"]
    assert approved[0].payload["approver"] == "Petrov"
    assert approved[0].payload["approved_at"].endswith("+00:00")

    result = invoke("status", "--project", project_dir)
    assert "release" in result.output and state.refs["release"] in result.output


@pytest.mark.parametrize("role", ["boss", "", "customer_lawyer"])
def test_approve_rejects_unknown_role(tmp_path, role) -> None:
    project_dir = init_project(tmp_path)
    _spec_ready(project_dir)
    assert invoke("prepare-release", "--project", project_dir).exit_code == 0
    result = invoke("approve", "--project", project_dir, "--approver", "Petrov",
                    "--role", role, "--sha", "0" * 64)
    assert result.exit_code == 1
    assert "Ошибка" in result.output and "Traceback" not in result.output
    assert Phase.RELEASE not in load_state(Project.load(project_dir)).completed


def _failing_report() -> ParityReport:
    return ParityReport(total=2, passed=1, critical_total=1, critical_passed=0,
                        unstable=[], results=[])


def test_build_exits_2_when_parity_threshold_not_met(tmp_path, monkeypatch) -> None:
    project_dir = init_project(tmp_path)
    monkeypatch.setattr(pipeline, "build_gateway", lambda project: None)
    monkeypatch.setattr(pipeline, "run_build_loop", lambda *a, **k: _failing_report())
    result = invoke("build", "--project", project_dir)
    assert result.exit_code == 2
    assert "Паритет: 1/2" in result.output
    assert "Ошибка" not in result.output
    assert "Порог не достигнут." in result.output


def test_build_reports_skipped_and_withheld(tmp_path, monkeypatch) -> None:
    project_dir = init_project(tmp_path)
    report = _failing_report().model_copy(
        update={"skipped_unsafe": ["s3", "s4"], "withheld_mismatches": 5})
    monkeypatch.setattr(pipeline, "build_gateway", lambda project: None)
    monkeypatch.setattr(pipeline, "run_build_loop", lambda *a, **k: report)
    result = invoke("build", "--project", project_dir)
    assert "Пропущено сценариев с записью (цель не песочница): 2" in result.output
    assert "Расхождений по удержанным значениям: 5" in result.output


def test_build_exits_0_when_parity_threshold_met(tmp_path, monkeypatch) -> None:
    project_dir = init_project(tmp_path)
    ok = ParityReport(total=1, passed=1, critical_total=0, critical_passed=0,
                      unstable=[], results=[])
    monkeypatch.setattr(pipeline, "build_gateway", lambda project: None)
    monkeypatch.setattr(pipeline, "run_build_loop", lambda *a, **k: ok)
    result = invoke("build", "--project", project_dir)
    assert result.exit_code == 0, result.output
    assert "Порог достигнут." in result.output
    [line] = [x for x in result.output.splitlines() if x.startswith("Рабочий каталог клона:")]
    workspace = Path(line.split(": ", 1)[1])
    assert workspace.parent == (tmp_path / "projects" / ".workspaces").resolve()
    assert "cli-demo" not in line


@pytest.mark.parametrize(
    "exc", [OSError("disk full"), PlaywrightError("Executable doesn't exist")]
)
def test_environment_errors_are_reported(tmp_path, monkeypatch, exc) -> None:
    project_dir = init_project(tmp_path)

    def boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr(pipeline, "run_observe", boom)
    result = invoke("observe", "--project", project_dir)
    assert result.exit_code == 1
    assert "Ошибка окружения" in result.output
    assert "Traceback" not in result.output


# --- bench --------------------------------------------------------------------------------


def test_bench_without_live_explains_and_exits_1(tmp_path, monkeypatch) -> None:
    from reverseai.bench import runner as bench_runner

    monkeypatch.setattr(bench_runner, "run_benchmark",
                        lambda *a, **k: pytest.fail("must not run offline from the CLI"))
    result = invoke("bench", "--target", "taskboard", "--workdir", tmp_path / "b")
    assert result.exit_code == 1
    assert "только в тестах" in result.output


def test_bench_live_prints_summary(tmp_path, monkeypatch) -> None:
    from reverseai.bench import runner as bench_runner
    from reverseai.bench.runner import BenchResult

    calls: dict = {}

    def fake_run(target, *, gateway, workdir, sandbox_factory):
        calls.update(target=target, gateway=gateway, workdir=workdir,
                     sandbox=sandbox_factory(workdir / "ws"))
        result = BenchResult(target=target, scenarios=12, parity_ratio=0.96, critical_ratio=1.0,
                             hidden_passed=25, hidden_total=26, cost_usd=1.2345,
                             duration_s=321.0, similarity_max=0.0123)
        workdir.mkdir(parents=True)
        (workdir / "bench_result.json").write_text(result.model_dump_json(), encoding="utf-8")
        return result

    monkeypatch.setattr(bench_runner, "run_benchmark", fake_run)
    workdir = tmp_path / "b"
    result = invoke("bench", "--target", "taskboard", "--live", "--workdir", workdir)
    assert result.exit_code == 0, result.output
    assert calls["target"] == "taskboard"
    assert calls["workdir"] == workdir
    assert calls["gateway"] is pipeline.build_gateway
    assert calls["sandbox"].workdir == workdir / "ws"
    out = result.output
    assert "Сценариев: 12" in out
    assert "Паритет: 96.00%" in out
    assert "критичные: 100.00%" in out
    assert "Скрытые тесты: 25/26" in out
    assert "Стоимость, USD: 1.2345" in out
    assert "Максимальное сходство кода: 0.0123" in out
    assert str(workdir / "bench_result.json") in out


def _released_with(project_dir: Path, method: str) -> None:
    project = Project.load(project_dir)
    scenario = Scenario(id="s1", title="t", steps=[
        ScenarioStep(step=Step(method=method, path="/api/tasks"), expect=Expect(status=200)),
    ])
    state = load_state(project)
    state.refs["release"] = project.store.put_json(
        Zone.RELEASED, "release_package", "release:t",
        {"scenarios": [scenario.model_dump(mode="json")]}).id
    save_state(project, state)


@pytest.mark.parametrize(("sandbox", "method", "refused"), [
    (True, "POST", True), (True, "GET", False), (False, "POST", False),
])
def test_build_refuses_unresettable_writes(tmp_path, monkeypatch, sandbox, method,
                                           refused) -> None:
    project_dir = init_project(tmp_path, target_is_sandbox=sandbox)
    _released_with(project_dir, method)
    ok = ParityReport(total=1, passed=1, critical_total=0, critical_passed=0,
                      unstable=[], results=[])
    monkeypatch.setattr(pipeline, "build_gateway", lambda project: None)
    monkeypatch.setattr(pipeline, "run_build_loop", lambda *a, **k: ok)
    result = invoke("build", "--project", project_dir)
    if refused:
        assert result.exit_code == 1
        assert "Ошибка" in result.output and "--allow-unstable" in result.output
        result = invoke("build", "--project", project_dir, "--allow-unstable")
    assert result.exit_code == 0, result.output



@pytest.mark.parametrize(("sim_ok", "hits", "code"), [
    (True, [], 0), (False, [], 2), (True, ["main.py:3"], 2),
])
def test_audit_exits_2_on_similarity_or_brand_mentions(tmp_path, monkeypatch, sim_ok, hits,
                                                       code) -> None:
    from reverseai.audit.similarity import SimilarityReport

    project_dir = init_project(tmp_path)
    result = pipeline.AuditResult(
        zip_path=tmp_path / "e.zip",
        similarity=SimilarityReport(0.05, 0.01 if sim_ok else 0.4, {}, sim_ok),
        brand_hits=hits,
    )
    monkeypatch.setattr(pipeline, "run_audit", lambda *a, **k: result)
    out = invoke("audit", "--project", project_dir, "--out", tmp_path / "out")
    assert out.exit_code == code, out.output
    assert f"Пакет доказательств: {tmp_path / 'e.zip'}" in out.output
    if code == 2:
        assert "Аудит не пройден" in out.output


@pytest.mark.parametrize("approver", ["", "   "])
def test_approve_requires_an_approver_name(tmp_path, approver) -> None:
    project_dir = init_project(tmp_path)
    _spec_ready(project_dir)
    assert invoke("prepare-release", "--project", project_dir).exit_code == 0
    sha = pipeline.draft_sha256(Project.load(project_dir))
    result = invoke("approve", "--project", project_dir, "--approver", approver,
                    "--role", "operator", "--sha", sha)
    assert result.exit_code == 1
    assert "Ошибка" in result.output and "Traceback" not in result.output
    assert Phase.RELEASE not in load_state(Project.load(project_dir)).completed
