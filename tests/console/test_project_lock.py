"""The project lock (D-015): one mutating command or console job per project at a time,
across processes. A second one is refused at once, in Russian."""

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reverseai import pipeline
from reverseai.cli import app as cli_app
from reverseai.pipeline import Phase, load_state

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


@pytest.fixture
def console_lang() -> str:
    return "ru"


PROJECT_URL = "/projects/console-demo"
BUSY = "проект занят другим процессом"

_HOLDER = """
import sys, time
from pathlib import Path
from reverseai.project import project_lock
with project_lock(Path(sys.argv[1])):
    print("locked", flush=True)
    sys.stdin.read()  # until the test closes stdin
"""


@contextmanager
def held_by_another_process(project_dir: Path) -> Iterator[None]:
    holder = subprocess.Popen([sys.executable, "-c", _HOLDER, str(project_dir)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        yield
    finally:
        assert holder.stdin is not None
        holder.stdin.close()
        holder.wait(timeout=10)


def test_cli_command_is_refused_while_another_process_holds_the_project(stage_root) -> None:
    project_dir = stage_root("observed") / "console-demo"
    with held_by_another_process(project_dir):
        result = CliRunner().invoke(cli_app, ["oracle", "--project", str(project_dir)])
        assert result.exit_code == 1
        assert BUSY in result.output and "Traceback" not in result.output
        assert Phase.ORACLE not in load_state(pipeline_project(project_dir)).completed
    result = CliRunner().invoke(cli_app, ["oracle", "--project", str(project_dir)])
    assert result.exit_code == 0, result.output


def pipeline_project(project_dir: Path):
    from reverseai.project import Project

    return Project.load(project_dir)


@pytest.mark.parametrize("command", [
    ["spec"], ["prepare-release"], ["build"], ["audit", "--out", "OUT"],
    ["approve", "--approver", "x", "--role", "operator", "--sha", "0"],
    ["observe"],
])
def test_every_mutating_cli_command_takes_the_lock(stage_root, tmp_path, command) -> None:
    project_dir = stage_root("observed") / "console-demo"
    args = [str(tmp_path) if a == "OUT" else a for a in command]
    with held_by_another_process(project_dir):
        result = CliRunner().invoke(cli_app, [*args, "--project", str(project_dir)])
    assert result.exit_code == 1, result.output
    assert BUSY in result.output


def test_console_job_is_refused_while_the_cli_holds_the_project(console) -> None:
    c = console("observed")
    with held_by_another_process(c.root / "console-demo"):
        r = c.post(f"{PROJECT_URL}/run/oracle")
        assert r.status_code == 409
        assert BUSY in r.text
        assert c.ctx.jobs.current("console-demo") is None
    r = c.post(f"{PROJECT_URL}/run/oracle")
    assert r.status_code == 303
    assert c.wait().status == "succeeded"


def test_console_job_fails_in_russian_if_the_lock_is_taken_after_the_check(
    console, monkeypatch
) -> None:
    from reverseai.console.routes import phases

    c = console("observed")
    monkeypatch.setattr(phases, "ensure_free", lambda project: None)  # lose the race
    with held_by_another_process(c.root / "console-demo"):
        c.post(f"{PROJECT_URL}/run/oracle")
        job = c.wait()
    assert job.status == "failed"
    assert job.message.startswith(f"Ошибка: {BUSY}")
    assert Phase.ORACLE not in load_state(c.project()).completed


def test_console_approval_is_refused_while_another_process_holds_the_project(console) -> None:
    c = console("prepared")
    sha = pipeline.draft_sha256(c.project())
    form = {"approver": "Анна", "role": "operator", "confirm": "on", "sha": sha}
    with held_by_another_process(c.root / "console-demo"):
        r = c.post(f"{PROJECT_URL}/release/approve", form)
        assert r.status_code == 409
        assert BUSY in r.text
    assert Phase.RELEASE not in load_state(c.project()).completed
    r = c.post(f"{PROJECT_URL}/release/approve", form)
    assert r.status_code == 303
    assert Phase.RELEASE in load_state(c.project()).completed
