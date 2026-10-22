"""Running pipeline phases from the console: background jobs calling the CLI's functions."""

import threading

import pytest
from typer.testing import CliRunner

from reverseai import pipeline
from reverseai.cli import app as cli_app
from reverseai.console.context import production_gateway
from reverseai.pipeline import Phase, load_state
from reverseai.project import Project

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


@pytest.fixture
def console_lang() -> str:
    return "ru"


PROJECT_URL = "/projects/console-demo"


def _tail(events, start):
    """Ledger events after `start`, without timestamps and hashes (comparable across runs)."""
    return [(e.type, e.zone, e.actor, e.payload) for e in events[start:]]


def test_run_oracle_completes_the_phase(console) -> None:
    c = console("observed")
    r = c.post(f"{PROJECT_URL}/run/oracle")
    assert r.status_code == 303
    assert r.headers["location"] == f"{PROJECT_URL}#job"
    job = c.wait()
    assert job.status == "succeeded", job.message
    assert job.label == "Оракул поведения"
    assert "Этап «Оракул поведения» (oracle) завершён." in job.log
    assert Phase.ORACLE in load_state(c.project()).completed


def test_console_and_cli_have_identical_ledger_effects(console, stage_root) -> None:
    c = console("observed")
    start = len(c.project().ledger.events())
    c.post(f"{PROJECT_URL}/run/oracle")
    assert c.wait().status == "succeeded"
    via_console = _tail(c.project().ledger.events(), start)

    cli_root = stage_root("observed")
    result = CliRunner().invoke(cli_app, ["oracle", "--project", str(cli_root / "console-demo")])
    assert result.exit_code == 0, result.output
    via_cli = _tail(Project.load(cli_root / "console-demo").ledger.events(), start)
    assert via_console == via_cli


def test_job_status_endpoint_and_job_panel(console) -> None:
    c = console("observed")
    assert c.get(f"{PROJECT_URL}/job").json() == {"job": None}
    c.post(f"{PROJECT_URL}/run/oracle")
    c.wait()
    data = c.get(f"{PROJECT_URL}/job").json()["job"]
    assert data["action"] == "oracle" and data["status"] == "succeeded"
    assert data["log"]
    html = c.get(PROJECT_URL).text
    assert 'id="job"' in html
    assert 'data-job-status="succeeded"' in html
    assert f'data-job-url="{PROJECT_URL}/job"' in html
    assert "Этап «Оракул поведения» (oracle) завершён." in html


def test_phase_order_error_is_a_russian_message(console) -> None:
    c = console("created")
    c.post(f"{PROJECT_URL}/run/spec")
    job = c.wait()
    assert job.status == "failed"
    assert job.message == "Ошибка: сначала завершите этап «Оракул поведения» (oracle)"
    html = c.get(PROJECT_URL).text
    assert "сначала завершите этап «Оракул поведения» (oracle)" in html
    assert "Traceback" not in html


def test_spec_with_the_injected_gateway(console) -> None:
    c = console("observed")
    c.post(f"{PROJECT_URL}/run/oracle")
    c.wait()
    c.post(f"{PROJECT_URL}/run/spec")
    job = c.wait()
    assert job.status == "succeeded", job.message
    assert Phase.SPEC in load_state(c.project()).completed
    assert any(e.type == "llm.call" for e in c.project().ledger.events())


def test_spec_without_provider_keys_reports_a_russian_error(console, monkeypatch) -> None:
    for name in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ZAI_API_KEY"]:
        monkeypatch.delenv(name, raising=False)
    c = console("observed", gateway_factory=production_gateway)
    c.post(f"{PROJECT_URL}/run/oracle")
    c.wait()
    c.post(f"{PROJECT_URL}/run/spec")
    job = c.wait()
    assert job.status == "failed"
    assert job.message.startswith("Ошибка: не задан ключ ни одного провайдера LLM")
    assert "ANTHROPIC_API_KEY" in job.message
    assert not any(e.type == "llm.call" for e in c.project().ledger.events())


def test_production_gateway_with_a_key(monkeypatch, console) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    c = console("created")
    gateway = production_gateway(c.project())
    assert gateway is not None


def test_observe_passes_the_form_options(console, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(pipeline, "run_observe",
                        lambda project, **kw: calls.append((project.dir.name, kw)))
    c = console("created")
    c.post(f"{PROJECT_URL}/run/observe",
           {"max_pages": "7", "submit_forms": "on", "probe": "on"})
    job = c.wait()
    assert job.status == "succeeded", job.message
    assert calls == [("console-demo", {"max_pages": 7, "submit_forms": True, "probe": True})]
    assert "Этап «Наблюдение» (observe) завершён." in job.log


def test_observe_defaults_match_the_cli(console, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(pipeline, "run_observe", lambda project, **kw: calls.append(kw))
    c = console("created")
    c.post(f"{PROJECT_URL}/run/observe")
    c.wait()
    assert calls == [{"max_pages": 50, "submit_forms": False, "probe": False}]


def test_observe_bad_number_is_refused_before_a_job_starts(console) -> None:
    c = console("created")
    r = c.post(f"{PROJECT_URL}/run/observe", {"max_pages": "0"})
    assert r.status_code == 400
    assert "Число страниц должно быть целым числом от 1" in r.text
    assert c.ctx.jobs.current("console-demo") is None


def test_unknown_action_is_404(console) -> None:
    assert console("created").post(f"{PROJECT_URL}/run/release").status_code == 404


def test_prepare_release_logs_the_draft_and_its_hash(console) -> None:
    c = console("specced")
    c.post(f"{PROJECT_URL}/run/prepare-release")
    job = c.wait()
    assert job.status == "succeeded", job.message
    sha = pipeline.draft_sha256(c.project())
    assert f"SHA-256 пакета (спецификация + сценарии): {sha}" in job.log
    assert any(line.startswith("Черновик для согласования:") for line in job.log)


def test_build_is_refused_without_allow_unstable(console) -> None:
    c = console("released")
    c.post(f"{PROJECT_URL}/run/build", {"max_rounds": "1"})
    job = c.wait()
    assert job.status == "failed"
    assert "результаты паритета будут нестабильны" in job.message
    assert "«Разрешить нестабильный прогон»" in job.message
    assert Phase.IMPLEMENT not in load_state(c.project()).completed


def test_build_and_audit_through_the_console(console) -> None:
    c = console("released")
    c.post(f"{PROJECT_URL}/run/build", {"max_rounds": "1", "allow_unstable": "on"})
    job = c.wait()
    assert job.status in ("succeeded", "attention"), job.message
    assert job.log[0] == "Внимание: LocalSandbox не изолирует код клона от этой машины."
    assert any(line.startswith("Паритет: ") for line in job.log)
    state = load_state(c.project())
    assert Phase.PARITY in state.completed
    assert state.parity_rounds == 1
    if job.status == "attention":
        assert job.message == "Порог не достигнут."

    c.post(f"{PROJECT_URL}/run/audit")
    job = c.wait()
    assert job.status in ("succeeded", "attention"), job.message
    assert any(line.startswith("Пакет доказательств: ") for line in job.log)
    assert "Этап «Аудит» (audit) завершён." in job.log
    assert (c.project().dir / "evidence" / "evidence_console-demo.zip").is_file()
    assert Phase.AUDIT in load_state(c.project()).completed


def test_one_job_per_project(console, monkeypatch) -> None:
    gate = threading.Event()
    monkeypatch.setattr(pipeline, "run_oracle", lambda project: gate.wait(10))
    c = console("observed")
    c.post(f"{PROJECT_URL}/run/oracle")
    r = c.post(f"{PROJECT_URL}/run/oracle")
    assert r.status_code == 409
    assert "Для проекта уже выполняется задача «Оракул поведения»" in r.text
    html = c.get(PROJECT_URL).text
    assert 'data-job-status="running"' in html
    assert "disabled" in html  # run buttons are disabled while a job runs
    gate.set()
    assert c.wait().status == "succeeded"


def test_run_buttons_follow_the_completed_phases(console) -> None:
    html = console("observed").get(PROJECT_URL).text
    assert f'action="{PROJECT_URL}/run/oracle"' in html
    assert 'data-ready="oracle"' in html
    assert 'data-ready="spec"' not in html
    assert "Повторный запуск этапа сбрасывает все следующие этапы." in html
