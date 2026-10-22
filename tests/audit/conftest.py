from pathlib import Path

import pytest

from reverseai.barrier.release import Approval, prepare_release, release
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.project import Attestation, Mode, Project, ProjectCard, create_project
from reverseai.spec.model import AnalystDraft, BehaviorSpec
from reverseai.zones.store import Zone

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
TASKBOARD_APP_JS = ROOT / "bench" / "targets" / "taskboard" / "static" / "app.js"


@pytest.fixture
def project_after_release(tmp_path) -> Project:
    """A project whose spec went through the real barrier (expression -> prepare -> release)."""
    card = ProjectCard(
        name="Audit Demo",
        mode=Mode.IMPORT_SUBSTITUTION,
        target_base_url="https://app.example.com/",
        allowed_domains=["app.example.com"],
        attestation=Attestation(
            lawful_access=True, basis="own contract", signed_by="Ivan",
            signed_at="2026-10-20T10:00:00Z",
        ),
        brand_terms=["TaskBoard Pro"],
        product_name="Tasklet",
    )
    project = create_project(card, tmp_path / "projects")
    project.store.put(
        Zone.DIRTY, "expression", "app.js", TASKBOARD_APP_JS.read_bytes(),
        {"url": "https://app.example.com/static/app.js"},
    )
    draft = AnalystDraft.model_validate_json(
        (FIXTURES / "llm" / "analyst_spec.json").read_text(encoding="utf-8")
    )
    spec = BehaviorSpec(product_name="Tasklet", api=[], **draft.model_dump())
    scenarios = [
        Scenario(id="S-001", title="Create a task", critical=True, steps=[
            ScenarioStep(
                step=Step(method="POST", path="/api/tasks", json_body={"title": "Buy milk"}),
                expect=Expect(status=201, json_equals={"/title": "Buy milk"}),
            ),
        ]),
    ]
    draft_ref = prepare_release(project, spec, scenarios)
    draft_json = project.store.get_json(draft_ref.id, Zone.DIRTY)
    assert not draft_json["report"]["findings"]
    release(project, draft_ref.id, Approval(
        approver="Petrov", role="operator", approved_at="2026-10-21T09:00:00Z",
        package_sha256=draft_json["package_sha256"],
    ))
    project.ledger.append("llm.call", "dirty", "analyst", {
        "role": "analyst", "model": "m-1", "provider": "p", "usage": {}, "cost_usd": 0.5,
    })
    project.ledger.append("llm.call", "dirty", "analyst", {
        "role": "analyst", "model": "m-1", "provider": "p", "usage": {}, "cost_usd": 0.25,
    })
    return project

