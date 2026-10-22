"""Background job runner: one active job per project, Russian outcomes, no secrets."""

import threading

import pytest

from reverseai.barrier.release import ReleaseError
from reverseai.console.jobs import JobBusy, JobRunner
from reverseai.messages import PlainError
from reverseai.pipeline import Phase, PhaseOrderError


def test_successful_job_records_log_times_and_status() -> None:
    runner = JobRunner()

    def work(log):
        log("шаг 1")
        log("шаг 2")

    job = runner.start("p", "oracle", "Оракул поведения", work)
    done = runner.wait("p", timeout=5)
    assert done is job
    assert job.status == "succeeded"
    assert job.log == ["шаг 1", "шаг 2"]
    assert job.started_at <= job.finished_at
    assert job.message is None
    assert runner.current("p") is job


def test_job_returning_a_message_needs_attention() -> None:
    runner = JobRunner()
    runner.start("p", "build", "Сборка", lambda log: "Порог не достигнут.")
    job = runner.wait("p", timeout=5)
    assert job.status == "attention"
    assert job.message == "Порог не достигнут."


@pytest.mark.parametrize(
    ("exc", "message"),
    [
        (PhaseOrderError(Phase.SPEC), "Ошибка: сначала завершите этап «Спецификация» (spec)"),
        (ReleaseError("bad hash"), "Ошибка: выпуск через барьер отклонён: bad hash"),
        (PlainError("готовое сообщение"), "Ошибка: готовое сообщение"),
        (OSError("disk full"), "Ошибка окружения: disk full"),
    ],
)
def test_expected_failures_become_russian_messages(exc, message) -> None:
    runner = JobRunner()

    def work(log):
        raise exc

    runner.start("p", "x", "X", work)
    job = runner.wait("p", timeout=5)
    assert job.status == "failed"
    assert job.message == message


def test_unexpected_failure_shows_no_traceback() -> None:
    runner = JobRunner()

    def work(log):
        raise KeyError("internal detail")

    runner.start("p", "x", "X", work)
    job = runner.wait("p", timeout=5)
    assert job.status == "failed"
    assert job.message.startswith("Внутренняя ошибка (KeyError)")
    assert "Traceback" not in job.message and "internal detail" not in job.message


def test_one_active_job_per_project() -> None:
    runner = JobRunner()
    release = threading.Event()
    runner.start("p", "x", "X", lambda log: release.wait(5) and None)
    with pytest.raises(JobBusy) as busy:
        runner.start("p", "y", "Y", lambda log: None)
    assert busy.value.job.action == "x"
    other = runner.start("q", "y", "Y", lambda log: None)  # another project is independent
    assert runner.wait("q", timeout=5) is other
    release.set()
    assert runner.wait("p", timeout=5).status == "succeeded"
    runner.start("p", "y", "Y", lambda log: None)  # free again
    assert runner.wait("p", timeout=5).action == "y"


def test_secrets_are_redacted_from_log_and_message() -> None:
    runner = JobRunner(secrets=lambda: ["sk-very-secret"])

    def work(log):
        log("key sk-very-secret in a line")
        raise RuntimeError("provider said sk-very-secret")

    runner.start("p", "x", "X", work)
    job = runner.wait("p", timeout=5)
    assert job.log == ["key *** in a line"]
    assert "sk-very-secret" not in job.message


def test_log_keeps_only_the_tail() -> None:
    runner = JobRunner(max_log_lines=3)
    runner.start("p", "x", "X", lambda log: [log(str(i)) for i in range(10)] and None)
    assert runner.wait("p", timeout=5).log == ["7", "8", "9"]


def test_job_as_json() -> None:
    runner = JobRunner()
    runner.start("p", "oracle", "Оракул поведения", lambda log: log("ok"))
    data = runner.wait("p", timeout=5).as_json()
    assert data["action"] == "oracle"
    assert data["label"] == "Оракул поведения"
    assert data["status"] == "succeeded"
    assert data["status_label"] == "завершено"
    assert data["log"] == ["ok"]
    assert data["started_at"] and data["finished_at"]


def test_wait_without_job_returns_none() -> None:
    assert JobRunner().wait("nobody", timeout=0.1) is None


def test_validation_error_in_a_job_is_one_russian_line(console, monkeypatch) -> None:
    from reverseai import pipeline

    def broken_state(project):
        pipeline.PipelineState.model_validate_json('{"completed": ["bogus"], "refs": {}}')

    monkeypatch.setattr(pipeline, "run_oracle", broken_state)
    c = console("observed")
    c.post("/projects/console-demo/run/oracle")
    job = c.wait()
    assert job.status == "failed"
    assert job.message is not None and "\n" not in job.message
    assert "errors.pydantic.dev" not in job.message
    assert job.message.startswith("Ошибка: некорректные данные (PipelineState): ")
    assert "completed.0 — недопустимое значение" in job.message
