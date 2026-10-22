"""Parity and evidence page, and the evidence pack download."""

import io
import json
import re
import zipfile

from reverseai.parity.differential import ParityReport
from reverseai.pipeline import load_state
from reverseai.zones.store import Zone

URL = "/projects/console-demo/parity"


def _report(project) -> ParityReport:
    ref = load_state(project).refs["parity_report"]
    return ParityReport.model_validate(project.store.get_json(ref, Zone.VERIFIER))


def test_parity_page_kpis_and_scenarios(console) -> None:
    c = console("audited")
    report = _report(c.project())
    html = c.get(URL).text
    for label in ["ПАРИТЕТ", "КРИТИЧНЫЕ", "НЕСТАБИЛЬНЫЕ", "РАУНДЫ"]:
        assert label in html
    assert f"{report.ratio:.3f}" in html
    assert f"{report.passed} из {report.total}" in html
    assert "ПОРОГ ПРОЙДЕН" in html
    rows = re.findall(r'<tr data-scenario="([^"]+)"', html)
    assert rows == [r.id for r in report.results]
    assert html.count(">PASS<") >= 2 * report.passed
    assert f"Расхождений по удержанным значениям: {report.withheld_mismatches}" in html


def test_similarity_brand_and_evidence(console) -> None:
    c = console("audited")
    project = c.project()
    pack = project.dir / "evidence" / "evidence_console-demo"
    similarity = json.loads((pack / "similarity_report.json").read_text(encoding="utf-8"))
    html = c.get(URL).text
    assert "СХОДСТВО КОДА" in html
    assert f"{similarity['max_score']:.3f}" in html
    assert f"порог {similarity['threshold']:.2f}" in html
    assert 'role="img"' in html and "aria-label=\"Сходство" in html
    assert "Упоминаний бренда не найдено" in html
    assert "evidence_console-demo.zip" in html
    for name in ["README.md", "ledger.jsonl", "parity_report.json", "similarity_report.json",
                 "zones_access.json"]:
        assert name in html
    assert "Песочница реализации не изолирована (LocalSandbox)" in html
    assert "Документ не является юридическим заключением." in html
    assert 'href="/projects/console-demo/evidence.zip"' in html


def test_evidence_download(console) -> None:
    c = console("audited")
    r = c.get("/projects/console-demo/evidence.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert 'filename="evidence_console-demo.zip"' in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        assert "README.md" in archive.namelist()


def test_evidence_download_before_audit_is_404(console) -> None:
    r = console("released").get("/projects/console-demo/evidence.zip")
    assert r.status_code == 404
    assert "Пакет доказательств ещё не собран" in r.text


def test_parity_page_before_parity(console) -> None:
    html = console("released").get(URL).text
    assert "Паритет ещё не проверялся" in html
    assert "Пакет доказательств ещё не собран" in html


def test_brand_mentions_are_listed(console) -> None:
    c = console("audited")
    project = c.project()
    # A brand term that the clone's code happens to contain (as the audit would report it).
    card_path = project.dir / "card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["brand_terms"] = ["FastAPI"]
    card_path.write_text(json.dumps(card), encoding="utf-8")
    html = c.get(URL).text
    assert "УПОМИНАНИЯ БРЕНДА" in html
    assert re.search(r"main\.py:\d+", html)


def _audit_elsewhere(c, out) -> None:
    """`reverseai audit --out <elsewhere>`: the console's evidence/ keeps the older pack."""
    from typer.testing import CliRunner

    from reverseai.cli import app as cli_app

    result = CliRunner().invoke(cli_app, ["audit", "--project", str(c.root / "console-demo"),
                                          "--out", str(out)])
    assert result.exit_code == 0, result.output


def test_a_pack_built_outside_the_console_is_not_shown_as_current(console, tmp_path) -> None:
    c = console("audited")
    _audit_elsewhere(c, tmp_path / "elsewhere")
    html = c.get(URL).text
    assert "Пакет собран вне консоли" in html
    assert 'href="/projects/console-demo/evidence.zip"' not in html
    assert "sha256 " not in html
    assert "СКАЧАТЬ" not in html
    assert "Аудит проведён вне консоли" in html  # similarity of the old pack is not shown
    overview = c.get("/projects/console-demo").text
    assert "Аудит проведён вне консоли" in overview
    r = c.get("/projects/console-demo/evidence.zip")
    assert r.status_code == 404
    assert "Пакет собран вне консоли" in r.text


def test_the_console_pack_is_shown_when_it_matches_the_latest_audit(console) -> None:
    c = console("audited")
    html = c.get(URL).text
    assert "собран вне консоли" not in html
    assert 'href="/projects/console-demo/evidence.zip"' in html
