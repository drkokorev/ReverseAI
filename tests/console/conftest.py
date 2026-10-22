"""Fixtures for the web console: a real project built by the pipeline on the bundled taskboard.

The pipeline runs once per session; each stage is snapshotted (the whole projects root is
copied), and every test works on its own copy of the stage it needs. The scripted LLM and the
recorded exchanges follow tests/test_pipeline.py and tests/e2e.
"""

from __future__ import annotations

import itertools
import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from reverseai import pipeline
from reverseai.barrier.release import Approval
from reverseai.bench.server import load_target, serve_asgi
from reverseai.config import load_settings
from reverseai.console import create_app
from reverseai.console.evidence import evidence_dir
from reverseai.implement.agent import AgentTurn, FileEdit
from reverseai.llm.gateway import Gateway
from reverseai.llm.providers import FakeProvider
from reverseai.llm.types import LLMRequest
from reverseai.observe.explorer import PageObservation
from reverseai.observe.har import Exchange
from reverseai.project import Attestation, Mode, Project, ProjectCard, create_project
from reverseai.sandbox import LocalSandbox

FIXTURES = Path(__file__).parent.parent / "fixtures"
PROJECT = "console-demo"
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
# Screenshots (tests/console/test_browser_smoke.py) are taken in CONSOLE_SCREENSHOTS_LANG; the
# demo approver's name follows it, so an English set shows no Russian data. Tests use Russian.
SCREENSHOTS_LANG = os.environ.get("CONSOLE_SCREENSHOTS_LANG", "ru")
APPROVER = "Peter Petrov" if SCREENSHOTS_LANG == "en" else "Пётр Петров"
STAGES = ("created", "observed", "specced", "prepared", "released", "audited")

taskboard = load_target("taskboard")


def respond_by_role(req: LLMRequest) -> str:
    role = (req.system or "").split("]")[0].removeprefix("[role:")
    if role not in TEXTS:
        raise AssertionError(f"unexpected role {role!r}")
    return TEXTS[role]


def fake_gateway(project: Project) -> Gateway:
    """The scripted LLM, logging to the project's ledger (what tests inject into the console)."""
    return Gateway(
        load_settings(),
        {"anthropic": FakeProvider(name="anthropic", responder=respond_by_role)},
        project.ledger,
        transcripts_dir=project.dir / "transcripts",
    )


def make_card(**over: Any) -> ProjectCard:
    base: dict[str, Any] = {
        "name": "Console Demo",
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


def _record(client: httpx.Client, base_url: str, script, prefix: str) -> list[Exchange]:
    exchanges = []
    for i, (method, path, body) in enumerate(script):
        r = client.request(method, path, json=body)
        exchanges.append(
            Exchange(
                id=f"{prefix}{i}", method=method, url=base_url + path, path=path, query={},
                status=r.status_code, request_json=body,
                response_json=r.json() if r.content else None,
                response_content_type=r.headers.get("content-type", ""),
            )
        )
    return exchanges


@pytest.fixture(scope="session")
def taskboard_server() -> Iterator[tuple[Any, str]]:
    app = taskboard.create_app()
    with serve_asgi(app) as url:
        yield app, url


@pytest.fixture(scope="session")
def snapshots(tmp_path_factory, taskboard_server) -> dict[str, Path]:
    """Projects roots, one per pipeline stage, all holding the same project `console-demo`."""
    app, url = taskboard_server
    base = tmp_path_factory.mktemp("console-stages")
    root = base / "work"
    snaps: dict[str, Path] = {}

    def snap(stage: str) -> None:
        snaps[stage] = base / stage
        shutil.copytree(root, snaps[stage])

    taskboard.reset_state(app)
    with httpx.Client(base_url=url, trust_env=False) as client:
        har_exchanges = _record(client, url, SCRIPT, "h")
        probe_exchanges = _record(client, url, PROBES, "p")
    taskboard.reset_state(app)

    card = make_card(target_base_url=url + "/", allowed_domains=["127.0.0.1"])
    project = create_project(card, root)
    pipeline.save_state(project, pipeline.load_state(project))  # as `reverseai init` does
    snap("created")
    page = PageObservation(url=url + "/", title="Board", links=[], forms=[], buttons=["Add"],
                           text_excerpt="tasks", screenshot_ref=None)
    pipeline.record_observation(project, pages=[page], har_exchanges=har_exchanges,
                                probe_exchanges=probe_exchanges)
    snap("observed")
    gateway = fake_gateway(project)
    pipeline.run_oracle(project)
    pipeline.run_spec(project, gateway)
    snap("specced")
    pipeline.run_prepare_release(project)
    snap("prepared")
    pipeline.run_release(project, Approval(
        approver=APPROVER, role="operator", approved_at="2026-10-22T09:00:00+00:00",
        package_sha256=pipeline.draft_sha256(project),
    ))
    snap("released")
    workspace = pipeline.workspace_dir(project)
    pipeline.run_build_loop(
        project, gateway, lambda: LocalSandbox(workspace), max_rounds=1,
        reset_original=lambda: taskboard.reset_state(app), delay_s=0.0,
    )
    pipeline.run_audit(project, evidence_dir(project))
    snap("audited")
    return snaps


@pytest.fixture
def stage_root(snapshots, tmp_path) -> Callable[[str], Path]:
    """Copy a stage snapshot into this test's tmp dir; returns the projects root."""

    copies = itertools.count(1)

    def copy(stage: str) -> Path:
        dst = tmp_path / f"projects-{stage}-{next(copies)}"
        shutil.copytree(snapshots[stage], dst)
        return dst

    return copy


class Harness:
    """A TestClient over a console on a projects root, plus shortcuts used by the tests."""

    def __init__(self, root: Path, **options: Any) -> None:
        options.setdefault("gateway_factory", fake_gateway)
        options.setdefault("sandbox_factory", LocalSandbox)
        self.root = root
        self.app = create_app(root, **options)
        self.client = TestClient(self.app)
        self.ctx = self.app.state.console

    @property
    def csrf(self) -> str:
        return self.ctx.csrf_token

    def project(self, name: str = PROJECT) -> Project:
        return self.ctx.projects.get(name)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.client.get(url, **kwargs)

    def post(self, url: str, data: dict | None = None, **kwargs: Any) -> httpx.Response:
        """POST a form with the CSRF token; redirects are not followed."""
        form = {"csrf": self.csrf, **(data or {})}
        return self.client.post(url, data=form, follow_redirects=False, **kwargs)

    def wait(self, name: str = PROJECT, timeout: float = 180.0):
        job = self.ctx.jobs.wait(name, timeout=timeout)
        assert job is not None, "no job was started"
        return job


@pytest.fixture
def console_lang() -> str:
    """The console's default language in a test; modules asserting Russian copy override it."""
    return "en"


@pytest.fixture
def console(stage_root, console_lang) -> Callable[..., Harness]:
    """`console(stage, **options)`: a Harness on a fresh copy of that pipeline stage."""

    def make(stage: str, **options: Any) -> Harness:
        options.setdefault("lang", console_lang)
        return Harness(stage_root(stage), **options)

    return make


@pytest.fixture
def project_name() -> str:
    return PROJECT


@pytest.fixture
def approver_name() -> str:
    """Who approved the release of the snapshot project (released and later stages)."""
    return APPROVER


@pytest.fixture
def scripted_gateway() -> Callable[[Project], Gateway]:
    """The scripted LLM gateway factory (no API keys needed)."""
    return fake_gateway
