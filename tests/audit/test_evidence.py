import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from reverseai.audit.evidence import build_evidence_pack
from reverseai.audit.similarity import SimilarityReport
from reverseai.parity.differential import ParityReport

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


def _parity() -> ParityReport:
    return ParityReport(
        total=4, passed=3, critical_total=1, critical_passed=1, unstable=["S-009"], results=[],
        skipped_unsafe=["S-010", "S-011"], withheld_mismatches=3,
    )


def _build(project, tmp_path) -> Path:
    similarity = SimilarityReport(0.05, 0.01, {"main.py": 0.01}, True)
    return build_evidence_pack(
        project, parity=_parity(), similarity=similarity,
        brand_hits=["src/a.py:2"], out_dir=tmp_path / "out",
    )


def test_evidence_pack_contents(project_after_release, tmp_path):
    project = project_after_release
    zip_path = _build(project, tmp_path)
    assert zip_path == tmp_path / "out" / "evidence_audit-demo.zip"

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        assert {
            "README.md", "ledger.jsonl", "ledger_verification.json", "sanitize_report.json",
            "parity_report.json", "similarity_report.json", "models_used.json",
            "zones_access.json",
        } <= names
        release_files = [n for n in names if n.startswith("release/")]
        assert len(release_files) == 1
        package = json.loads(archive.read(release_files[0]))
        assert package["approval"]["approver"] == "Petrov"

        verification = json.loads(archive.read("ledger_verification.json"))
        assert verification["ok"] is True
        readme = archive.read("README.md").decode("utf-8")
        assert json.loads(archive.read("sanitize_report.json")) == [{"findings": []}]
        models = json.loads(archive.read("models_used.json"))
        assert models == [{"model": "m-1", "provider": "p", "calls": 2, "cost_usd": 0.75}]
        access = json.loads(archive.read("zones_access.json"))
        assert {"id", "kind", "zone"} == set(access["verifier"][0])
        assert any(e["kind"] == "release_package" for e in access["verifier"])
        assert json.loads(archive.read("similarity_report.json"))["ok"] is True
        assert json.loads(archive.read("parity_report.json"))["total"] == 4

    for section in (
        "# Пакет доказательств: Tasklet", "## Целостность журнала", "## Одобрения",
        "## Паритет", "## Сходство кода", "## Упоминания бренда", "## Риски приёма",
        "## Модели", "Документ не является юридическим заключением",
    ):
        assert section in readme
    assert "Petrov" in readme and "src/a.py:2" in readme
    sha = package["approval"]["package_sha256"]
    assert f"sha256 пакета (спецификация + сценарии): {sha}" in readme
    assert "tos_review" in readme  # import-substitution intake risk flag
    assert "0.750" in readme  # parity ratio
    assert "Пропущено сценариев с записью (цель не песочница): 2" in readme
    assert "Расхождений по удержанным значениям: 3" in readme
    assert (tmp_path / "out" / "evidence_audit-demo" / "README.md").exists()


def test_evidence_pack_is_logged_and_repeatable(project_after_release, tmp_path):
    project = project_after_release
    zip_path = _build(project, tmp_path)
    event = project.ledger.events()[-1]
    assert event.type == "audit.evidence_pack"
    assert event.zone == "verifier" and event.actor == "audit"
    assert event.payload == {
        "zip": zip_path.name, "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(),
    }
    assert project.ledger.verify().ok
    _build(project, tmp_path)  # rebuilding over an existing pack must not fail
    assert project.ledger.verify().ok


def test_evidence_readme_states_whether_the_sandbox_was_isolated(project_after_release,
                                                                 tmp_path):
    project = project_after_release
    readme = _build(project, tmp_path).parent / "evidence_audit-demo" / "README.md"
    assert "Реализация не запускалась" in readme.read_text(encoding="utf-8")
    project.ledger.append("implement.start", "clean", "clean.implement",
                          {"release_ref": "r", "scenarios": 1, "sandbox_isolated": False})
    _build(project, tmp_path)
    text = readme.read_text(encoding="utf-8")
    assert "## Песочница реализации" in text
    assert "не изолирована" in text
    project.ledger.append("implement.start", "clean", "clean.implement",
                          {"release_ref": "r", "scenarios": 1, "sandbox_isolated": True})
    _build(project, tmp_path)
    text = readme.read_text(encoding="utf-8")
    assert "- Песочница: изолирована" in text


def _readme(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as archive:
        return archive.read("README.md").decode("utf-8")


def test_readme_is_russian_without_english_status_tokens(project_after_release, tmp_path):
    import re

    readme = _readme(_build(project_after_release, tmp_path))
    assert "- Статус: цел (проверка хэш-цепочки пройдена)" in readme
    assert "- Сходство ниже порога: да" in readme
    for token in ("ok", "True", "False"):
        assert not re.search(rf"\b{token}\b", readme), token


def test_readme_reports_a_tampered_ledger(project_after_release, tmp_path):
    project = project_after_release
    lines = project.ledger.path.read_bytes().split(b"\n")
    lines[1] = lines[1].replace(b'"zone": "dirty"', b'"zone": "clean"', 1)
    project.ledger.path.write_bytes(b"\n".join(lines))
    zip_path = _build(project, tmp_path)
    readme = _readme(zip_path)
    assert "- Статус: НАРУШЕНА" in readme
    assert "- Первая нарушенная запись: 1" in readme
    with zipfile.ZipFile(zip_path) as archive:
        assert json.loads(archive.read("ledger_verification.json"))["ok"] is False


def test_readme_without_any_release(tmp_path):
    from reverseai.project import Attestation, Mode, ProjectCard, create_project

    card = ProjectCard(
        name="Empty Demo", mode=Mode.LEGACY, target_base_url="https://app.example.com/",
        allowed_domains=["app.example.com"], product_name="Tasklet",
        attestation=Attestation(lawful_access=True, basis="b", signed_by="s", signed_at="t"),
    )
    project = create_project(card, tmp_path / "projects")
    similarity = SimilarityReport(0.05, 0.2, {"main.py": 0.2}, False)
    zip_path = build_evidence_pack(project, parity=_parity(), similarity=similarity,
                                   brand_hits=[], out_dir=tmp_path / "out")
    readme = _readme(zip_path)
    assert "- Одобренных релизов нет." in readme
    assert "- Реализация не запускалась." in readme
    assert "- Упоминаний не найдено." in readme
    assert "- Сходство ниже порога: нет" in readme
    with zipfile.ZipFile(zip_path) as archive:
        assert not [n for n in archive.namelist() if n.startswith("release/")]
        assert json.loads(archive.read("sanitize_report.json")) == []
