import json
from pathlib import Path

import pytest

from reverseai.barrier.release import Approval, prepare_release, release
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.project import Attestation, Mode, Project, ProjectCard, create_project
from reverseai.spec.model import AnalystDraft, BehaviorSpec
from reverseai.zones.store import Zone

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TARGET_HOST = "app.example.com"


def make_spec() -> BehaviorSpec:
    draft = AnalystDraft.model_validate_json(
        (FIXTURES / "llm" / "analyst_spec.json").read_text(encoding="utf-8")
    )
    return BehaviorSpec(product_name="Tasklet", api=[], **draft.model_dump())


def _step(method, path, status, body=None, equals=None, save=None, shape=None):
    return ScenarioStep(
        step=Step(method=method, path=path, json_body=body, save=save or {}),
        expect=Expect(status=status, json_equals=equals or {}, json_shape=shape),
    )


def make_scenarios() -> list[Scenario]:
    task_shape = {
        "type": "object",
        "required": ["id", "title", "priority", "done", "created_at"],
        "properties": {"id": {"type": "integer"}, "created_at": {"type": "string"}},
    }
    return [
        Scenario(id="S-001", title="Create and read a task", critical=True, steps=[
            _step("POST", "/api/tasks", 201, {"title": "  Buy milk  "},
                  {"/id": 1, "/title": "Buy milk", "/priority": "normal", "/done": False},
                  save={"id": "/id"}, shape=task_shape),
            _step("GET", "/api/tasks/{id}", 200, equals={"/title": "Buy milk"}),
            _step("GET", "/api/tasks", 200, equals={"/0/id": 1}),
        ]),
        Scenario(id="S-002", title="Duplicate open title", steps=[
            _step("POST", "/api/tasks", 201, {"title": "Buy milk", "priority": "high"}),
            _step("POST", "/api/tasks", 409, {"title": "buy MILK"}, {"/error": "duplicate"}),
        ]),
        Scenario(id="S-003", title="Validation errors", steps=[
            _step("POST", "/api/tasks", 422, {"title": "x" * 201},
                  {"/error": "title_too_long"}),
            _step("POST", "/api/tasks", 422, {"title": "Walk", "priority": "urgent"},
                  {"/error": "invalid_priority"}),
            _step("GET", "/api/stats", 200, equals={"/total": 0, "/done": 0, "/open": 0}),
        ]),
        Scenario(id="S-004", title="Complete and delete", steps=[
            _step("POST", "/api/tasks", 201, {"title": "Walk"}, save={"id": "/id"}),
            _step("PATCH", "/api/tasks/{id}", 200, {"done": True}, {"/done": True}),
            _step("GET", "/api/stats", 200, equals={"/total": 1, "/done": 1, "/open": 0}),
            _step("DELETE", "/api/tasks/{id}", 204),
            _step("GET", "/api/tasks/{id}", 404, equals={"/error": "not_found"}),
        ]),
    ]


def package(spec: BehaviorSpec, scenarios: list[Scenario]) -> dict:
    return {
        "spec": spec.model_dump(mode="json"),
        "scenarios": [s.model_dump(mode="json") for s in scenarios],
        "approval": {"approver": "Petrov", "role": "operator",
                     "approved_at": "2026-10-21T09:00:00Z", "package_sha256": "0" * 64},
        "sanitize_report": {"findings": []},
    }


@pytest.fixture
def project(tmp_path) -> Project:
    card = ProjectCard(
        name="Implement Demo",
        mode=Mode.LEGACY,
        target_base_url=f"https://{TARGET_HOST}/",
        allowed_domains=[TARGET_HOST],
        attestation=Attestation(
            lawful_access=True, basis="own contract", signed_by="Ivan",
            signed_at="2026-10-20T10:00:00Z",
        ),
        brand_terms=["TaskBoard Pro"],
        product_name="Tasklet",
    )
    return create_project(card, tmp_path / "projects")


@pytest.fixture
def released_project(project) -> tuple[Project, str]:
    """A project whose spec and scenarios went through the real barrier."""
    draft_ref = prepare_release(project, make_spec(), make_scenarios())
    draft = project.store.get_json(draft_ref.id, Zone.DIRTY)
    assert not draft["report"]["findings"]
    approval = Approval(
        approver="Petrov", role="operator", approved_at="2026-10-21T09:00:00Z",
        package_sha256=draft["package_sha256"],
    )
    ref = release(project, draft_ref.id, approval)
    released = project.store.get_json(ref.id, Zone.RELEASED)
    assert len(released["scenarios"]) == 4
    assert json.dumps(released["scenarios"]).count("Buy milk") >= 3  # values survived
    return project, ref.id


@pytest.fixture
def quick_release(project) -> tuple[Project, str]:
    """A package put straight into the RELEASED zone (no barrier run), for fast loop tests."""
    scenarios = make_scenarios()[:2]
    ref = project.store.put_json(
        Zone.RELEASED, "release_package", "release:quick", package(make_spec(), scenarios)
    )
    return project, ref.id
