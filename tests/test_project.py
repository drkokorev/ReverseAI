import json

import pytest

from reverseai.llm.policy import DataPolicy
from reverseai.project import (
    Attestation,
    IntakeError,
    Mode,
    Project,
    ProjectCard,
    create_project,
    risk_flags,
    slug,
)


def make_card(**over) -> ProjectCard:
    base: dict = {
        "name": "Demo Project",
        "mode": Mode.LEGACY,
        "target_base_url": "https://app.example.com/",
        "allowed_domains": ["app.example.com"],
        "attestation": Attestation(
            lawful_access=True,
            basis="own contract",
            signed_by="Ivan",
            signed_at="2026-10-20T10:00:00Z",
        ),
        "product_name": "Acme Board",
    }
    base.update(over)
    return ProjectCard(**base)


def test_requires_attestation(tmp_path):
    card = make_card(
        attestation=Attestation(
            lawful_access=False, basis="", signed_by="x", signed_at="2026-10-20"
        )
    )
    with pytest.raises(IntakeError):
        create_project(card, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_target_must_be_in_allowed_domains(tmp_path):
    card = make_card(allowed_domains=["other.example.com"])
    with pytest.raises(IntakeError):
        create_project(card, tmp_path)


def test_host_match_is_exact_and_case_insensitive(tmp_path):
    ok = make_card(
        target_base_url="https://APP.Example.com:8443/x", allowed_domains=["App.EXAMPLE.com"]
    )
    create_project(ok, tmp_path)
    evil = make_card(
        name="Evil",
        target_base_url="https://app.example.com.evil.io/",
        allowed_domains=["app.example.com"],
    )
    with pytest.raises(IntakeError):
        create_project(evil, tmp_path)


def test_product_name_cannot_reuse_brand(tmp_path):
    card = make_card(brand_terms=["TaskBoard Pro"], product_name="TaskBoard Lite")
    with pytest.raises(IntakeError):
        create_project(card, tmp_path)
    # the whole brand term inside a longer name is caught too, case-insensitively
    card = make_card(brand_terms=["Zoom"], product_name="My zoomer")
    with pytest.raises(IntakeError):
        create_project(card, tmp_path)
    # unrelated names pass; short generic words alone ("Pro") do not trigger
    create_project(make_card(brand_terms=["TaskBoard Pro"], product_name="Acme Pro"), tmp_path)


def test_import_substitution_flags():
    flags = risk_flags(make_card(mode=Mode.IMPORT_SUBSTITUTION))
    assert flags[:3] == ["patents", "trademarks", "tos_review"]
    assert "read_only_observation" in flags
    assert risk_flags(make_card(mode=Mode.IMPORT_SUBSTITUTION, target_is_sandbox=True)) == [
        "patents",
        "trademarks",
        "tos_review",
    ]
    assert risk_flags(make_card()) == ["read_only_observation"]
    assert risk_flags(make_card(target_is_sandbox=True)) == []


def test_slug():
    assert slug("My  Cool_Project!") == "my-cool-project"
    assert slug("Проект Один") == "проект-один"
    with pytest.raises(IntakeError):
        slug("!!!")


def test_existing_directory_rejected(tmp_path):
    create_project(make_card(), tmp_path)
    with pytest.raises(IntakeError):
        create_project(make_card(), tmp_path)


def test_create_and_load_roundtrip(tmp_path):
    card = make_card(
        mode=Mode.IMPORT_SUBSTITUTION,
        data_policy=DataPolicy(allowed_jurisdictions={"us", "self"}),
        brand_terms=["TaskBoard"],
    )
    project = create_project(card, tmp_path)
    assert project.dir == tmp_path / "demo-project"
    for rel in ("card.json", "ledger.jsonl", "artifacts", "state.json"):
        assert (project.dir / rel).exists()
    assert json.loads((project.dir / "state.json").read_text()) == {
        "completed": [],
        "refs": {},
        "parity_rounds": 0,
    }
    raw = json.loads((project.dir / "card.json").read_text())
    assert raw["data_policy"]["allowed_jurisdictions"] == ["self", "us"]

    events = project.ledger.events()
    assert events[0].type == "project.created"
    assert events[0].zone == "dirty"
    assert events[0].actor == "intake"
    assert events[0].payload["risk_flags"] == risk_flags(card)
    assert events[0].payload["name"] == "Demo Project"
    assert events[0].payload["mode"] == "import_substitution"
    assert events[0].payload["attestation"]["signed_by"] == "Ivan"

    loaded = Project.load(project.dir)
    assert loaded.card == card
    assert loaded.card.data_policy.allowed_jurisdictions == {"us", "self"}
    assert loaded.store.root == project.dir / "artifacts"
    assert loaded.ledger.events()[0].type == "project.created"
    assert Project(project.dir).card == card


def test_a_directory_created_concurrently_is_an_intake_error(tmp_path, monkeypatch):
    from pathlib import Path

    (tmp_path / "demo-project").mkdir()  # another process won the race after our check
    real_exists = Path.exists
    monkeypatch.setattr(
        Path, "exists", lambda self: False if self.name == "demo-project" else real_exists(self)
    )
    with pytest.raises(IntakeError, match="already exists"):
        create_project(make_card(), tmp_path)


def test_unknown_card_keys_are_rejected():
    from pydantic import ValidationError

    good = make_card().model_dump(mode="json")
    for key, value in (("brand_term", ["Acme"]), ("target_is_sanbox", True)):
        with pytest.raises(ValidationError, match="xtra"):
            ProjectCard.model_validate({**good, key: value})
    with pytest.raises(ValidationError, match="xtra"):
        ProjectCard.model_validate({**good, "attestation": {**good["attestation"], "x": 1}})
    assert ProjectCard.model_validate(good) == make_card()


def test_project_lock_refuses_a_second_holder_at_once(tmp_path) -> None:
    from reverseai.project import ProjectBusy, project_lock

    with project_lock(tmp_path):
        with pytest.raises(ProjectBusy) as info, project_lock(tmp_path):
            pass
        assert "проект занят другим процессом" in str(info.value)
    with project_lock(tmp_path):  # released: free again
        pass
    assert (tmp_path / "pipeline.lock").exists()
