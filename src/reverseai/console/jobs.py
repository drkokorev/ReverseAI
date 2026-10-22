"""In-process background jobs: a thread per job, at most one active job per project.

A job wraps one pipeline action. Its log holds short Russian lines written by the action (the
same lines the CLI prints); failures become one Russian message, never a traceback. Every line
and message is scrubbed of configured API keys before it is stored.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from reverseai.config import load_settings
from reverseai.messages import ENVIRONMENT_ERRORS, USER_ERRORS, user_message

_LOG = logging.getLogger("reverseai.console")

Status = Literal["running", "succeeded", "attention", "failed"]
STATUS_LABELS: dict[str, str] = {
    "running": "выполняется",
    "succeeded": "завершено",
    "attention": "требует внимания",
    "failed": "ошибка",
}
JobLog = Callable[[str], None]
# An action writes log lines and returns None (success) or a message that needs attention
# (what the CLI reports with exit code 2: parity threshold missed, audit failed).
Action = Callable[[JobLog], str | None]


def configured_secrets() -> list[str]:
    """Values of the API-key environment variables named in the settings."""
    names = {spec.api_key_env for spec in load_settings().providers.values() if spec.api_key_env}
    return [os.environ[name] for name in sorted(names) if os.environ.get(name)]


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


@dataclass
class Job:
    project: str
    action: str
    label: str
    max_log_lines: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: Status = "running"
    started_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    finished_at: dt.datetime | None = None
    message: str | None = None
    _lines: deque[str] = field(default_factory=deque)
    _done: threading.Event = field(default_factory=threading.Event)

    @property
    def log(self) -> list[str]:
        return list(self._lines)

    @property
    def running(self) -> bool:
        return self.status == "running"

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "label": self.label,
            "status": self.status,
            "status_label": self.status_label,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "message": self.message,
            "log": self.log,
        }


class JobBusy(RuntimeError):
    """The project already has a running job."""

    def __init__(self, job: Job) -> None:
        super().__init__(f"project {job.project!r} is busy with {job.action!r}")
        self.job = job


class JobRunner:
    def __init__(
        self,
        *,
        secrets: Callable[[], list[str]] = configured_secrets,
        max_log_lines: int = 200,
    ) -> None:
        self._secrets = secrets
        self._max_log_lines = max_log_lines
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}  # latest job per project

    def current(self, project: str) -> Job | None:
        with self._lock:
            return self._jobs.get(project)

    def busy(self, project: str) -> bool:
        job = self.current(project)
        return job is not None and job.running

    def start(self, project: str, action: str, label: str, work: Action) -> Job:
        with self._lock:
            previous = self._jobs.get(project)
            if previous is not None and previous.running:
                raise JobBusy(previous)
            job = Job(project=project, action=action, label=label,
                      max_log_lines=self._max_log_lines)
            self._jobs[project] = job
        thread = threading.Thread(
            target=self._run, args=(job, work), name=f"console-job-{project}-{action}",
            daemon=True,
        )
        thread.start()
        return job

    def wait(self, project: str, timeout: float | None = None) -> Job | None:
        """Block until the project's latest job finishes; None when it has no job."""
        job = self.current(project)
        if job is not None:
            job._done.wait(timeout)
        return job

    def _run(self, job: Job, work: Action) -> None:
        secrets = self._secrets()

        def log(line: str) -> None:
            job._lines.append(redact(str(line), secrets))
            while len(job._lines) > job.max_log_lines:
                job._lines.popleft()

        status: Status = "succeeded"
        message: str | None = None
        try:
            message = work(log)
            if message is not None:
                status = "attention"
        except USER_ERRORS as exc:
            status, message = "failed", f"Ошибка: {user_message(exc)}"
        except ENVIRONMENT_ERRORS as exc:
            status, message = "failed", f"Ошибка окружения: {exc}"
        except Exception as exc:  # noqa: BLE001 - shown as one line; details go to the server log
            _LOG.exception("console job %s/%s failed", job.project, job.action)
            status = "failed"
            message = (
                f"Внутренняя ошибка ({type(exc).__name__}). Подробности — в журнале сервера."
            )
        job.message = redact(message, secrets) if message is not None else None
        job.finished_at = dt.datetime.now(dt.UTC)
        job.status = status
        job._done.set()
