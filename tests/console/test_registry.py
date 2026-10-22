"""The console reads each project from disk per request: card edits apply, broken projects
are reported in Russian instead of failing the whole page."""

import json

import pytest
from typer.testing import CliRunner

from reverseai import pipeline
from reverseai.cli import app as cli_app
from reverseai.project import Project

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


@pytest.fixture
def console_lang() -> str:
    return "ru"


PROJECT_URL = "/projects/console-demo"


def _add_brand_term(root, term: str) -> None:
    path = root / "console-demo" / "card.json"
    card = json.loads(path.read_text(encoding="utf-8"))
    card["brand_terms"] = [*card["brand_terms"], term]
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")


def test_card_edits_after_start_apply_to_console_jobs_like_the_cli(console, stage_root) -> None:
    c = console("specced")
    assert c.get(PROJECT_URL).status_code == 200  # the project was read before the edit
    _add_brand_term(c.root, "task board")

    c.post(f"{PROJECT_URL}/run/prepare-release")
    job = c.wait()
    assert job.status == "succeeded", job.message
    console_draft = pipeline._draft(c.project())
    assert "task board" not in console_draft.spec.summary.lower()

    cli_root = stage_root("specced")
    _add_brand_term(cli_root, "task board")
    result = CliRunner().invoke(
        cli_app, ["prepare-release", "--project", str(cli_root / "console-demo")]
    )
    assert result.exit_code == 0, result.output
    cli_sha = pipeline.draft_sha256(Project.load(cli_root / "console-demo"))
    assert console_draft.package_sha256 == cli_sha


def _break_card(root) -> None:
    path = root / "console-demo" / "card.json"
    card = json.loads(path.read_text(encoding="utf-8"))
    card["brand_term"] = ["x"]  # a pre-D-014 typo: unknown keys are refused
    path.write_text(json.dumps(card), encoding="utf-8")


def _copy_project(root, name: str) -> None:
    import shutil

    shutil.copytree(root / "console-demo", root / name)


def test_projects_list_survives_a_broken_card(console) -> None:
    c = console("audited")
    _copy_project(c.root, "intact")
    _break_card(c.root)
    r = c.get("/")
    assert r.status_code == 200
    assert 'href="/projects/intact"' in r.text
    assert "карточка повреждена: brand_term — неизвестное поле" in r.text
    assert "ВСЕ ПРОЕКТЫ · 2" in r.text


def test_projects_list_survives_a_corrupt_state(console) -> None:
    c = console("audited")
    (c.root / "console-demo" / "state.json").write_text("{not json", encoding="utf-8")
    r = c.get("/")
    assert r.status_code == 200
    assert "состояние конвейера повреждено: некорректный JSON" in r.text


def test_broken_project_pages_are_a_russian_error(console) -> None:
    c = console("audited")
    _break_card(c.root)
    for url in [PROJECT_URL, f"{PROJECT_URL}/release", f"{PROJECT_URL}/parity",
                f"{PROJECT_URL}/costs", f"{PROJECT_URL}/job"]:
        r = c.get(url)
        assert r.status_code == 500, url
        assert "Проект повреждён" in r.text, url
        assert "brand_term — неизвестное поле" in r.text, url
        assert "Internal Server Error" not in r.text
    r = c.post(f"{PROJECT_URL}/run/oracle")
    assert r.status_code == 500 and "Проект повреждён" in r.text


def test_unexpected_errors_render_a_russian_500(console, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from reverseai.console.routes import costs

    def boom(events):
        raise KeyError("boom")

    monkeypatch.setattr(costs, "summarize_costs", boom)
    c = console("audited")
    client = TestClient(c.app, raise_server_exceptions=False)
    r = client.get(f"{PROJECT_URL}/costs")
    assert r.status_code == 500
    assert "Внутренняя ошибка" in r.text
    assert "журнале сервера" in r.text
    assert "boom" not in r.text
    assert r.headers["content-security-policy"].startswith("default-src 'self'")


def test_request_validation_errors_render_a_russian_page(console) -> None:
    c = console("created")
    r = c.client.post("/projects", data={"csrf": c.csrf},
                      files={"name": ("x.txt", b"x", "text/plain")}, follow_redirects=False)
    assert r.status_code == 400
    assert "Некорректный запрос" in r.text
    assert "detail" not in r.text


def test_project_names_are_url_encoded_in_links_and_redirects(console) -> None:
    import re

    c = console("observed")
    _copy_project(c.root, "demo #1?x")
    encoded = "/projects/demo%20%231%3Fx"
    listing = c.get("/").text
    assert f'href="{encoded}"' in listing
    page = c.get(encoded)
    assert page.status_code == 200
    hrefs = re.findall(r'(?:href|action|data-job-url)="(/projects/[^"]*)"', page.text)
    assert hrefs and all(h.startswith(encoded) for h in hrefs), hrefs
    r = c.post(f"{encoded}/run/oracle")
    assert r.status_code == 303 and r.headers["location"] == f"{encoded}#job"
    assert c.wait("demo #1?x").status == "succeeded"
