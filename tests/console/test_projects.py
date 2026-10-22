"""Projects list, new project form and the project overview."""

import json
import re

import pytest

from reverseai.pipeline import Phase, load_state
from reverseai.project import Project

GOOD_FORM = {
    "name": "Acme Orders",
    "mode": "legacy",
    "target_base_url": "https://orders.acme.test/",
    "allowed_domains": "orders.acme.test, api.acme.test",
    "target_is_sandbox": "on",
    "product_name": "Ordero",
    "brand_terms": "Acme Orders\nAcme",
    "jurisdictions": ["us", "eu"],
    "jurisdiction": "RU",
    "lawful_access": "on",
    "basis": "договор №1",
    "signed_by": "Иван Иванов",
    "signed_at": "2026-10-22T10:00:00Z",
}


def test_projects_list_shows_mode_host_progress_and_activity(console) -> None:
    c = console("audited")
    html = c.get("/").text
    assert "ПРОЕКТЫ" in html
    assert "Console Demo" in html
    assert "LEGACY" in html
    assert "127.0.0.1" in html
    assert "9 / 9" in html
    last = c.project().ledger.events()[-1].ts
    assert last[:10] in html and last[11:19] in html
    assert html.count('class="progress-step done"') == 9
    assert ".workspaces" not in html
    assert 'href="/projects/console-demo"' in html
    assert 'href="/projects/new"' in html


def test_projects_list_counts_partial_progress(console) -> None:
    html = console("specced").get("/").text
    assert "4 / 9" in html  # intake, observe, oracle, spec
    assert html.count('class="progress-step done"') == 4


def test_empty_projects_root(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from reverseai.console import create_app

    html = TestClient(create_app(tmp_path / "missing")).get("/").text
    assert "Проектов пока нет" in html


def test_new_project_form_lists_every_card_field(console) -> None:
    html = console("created").get("/projects/new").text
    for name in ["name", "mode", "target_base_url", "allowed_domains", "target_is_sandbox",
                 "product_name", "brand_terms", "jurisdictions", "jurisdiction",
                 "lawful_access", "basis", "signed_by", "signed_at"]:
        assert f'name="{name}"' in html, name
    assert "Импортозамещение" in html


def test_create_project_writes_the_card_and_logs_intake(console) -> None:
    c = console("created")
    r = c.post("/projects", GOOD_FORM)
    assert r.status_code == 303
    assert r.headers["location"] == "/projects/acme-orders"
    project = Project.load(c.root / "acme-orders")
    card = project.card
    assert card.allowed_domains == ["orders.acme.test", "api.acme.test"]
    assert card.brand_terms == ["Acme Orders", "Acme"]
    assert card.target_is_sandbox is True
    assert card.data_policy.allowed_jurisdictions == {"us", "eu"}
    assert card.attestation.signed_by == "Иван Иванов"
    # same effects as `reverseai init`: project.created, then intake completed
    types = [e.type for e in project.ledger.events()]
    assert types == ["project.created", "phase.completed"]
    assert load_state(project).completed == [Phase.INTAKE]
    assert "Acme Orders" in c.get("/").text


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"lawful_access": None}, "Нужно подтвердить законность доступа к цели"),
        ({"target_base_url": "https://other.test/"},
         "Хост цели «other.test» не входит в разрешённые домены"),
        ({"product_name": "Acme Orders Lite"},
         "Название продукта «Acme Orders Lite» повторяет бренд оригинала"),
        ({"name": "Console Demo"}, "Проект с таким именем уже существует"),
        ({"name": "!!!"}, "В названии проекта нет букв или цифр"),
        ({"name": ""}, "Укажите название проекта"),
        ({"product_name": " "}, "Укажите название продукта клона"),
        ({"allowed_domains": ""}, "Укажите хотя бы один разрешённый домен"),
        ({"mode": "other"}, "Неизвестный режим проекта"),
        ({"jurisdictions": []}, "Выберите хотя бы одну юрисдикцию"),
    ],
)
def test_intake_errors_are_shown_in_russian_next_to_the_form(console, change, message) -> None:
    c = console("created")
    form = {k: v for k, v in {**GOOD_FORM, **change}.items() if v is not None}
    r = c.post("/projects", form)
    assert r.status_code == 400
    assert message in r.text
    assert 'class="form-error"' in r.text
    assert 'name="name"' in r.text  # the form is shown again ...
    if form.get("basis"):
        assert form["basis"] in r.text  # ... with the values entered
    names = sorted(p.name for p in c.root.iterdir())
    assert "acme-orders" not in names and "acme-orders-lite" not in names


def test_overview_timeline_kpis_zones_and_ledger(console) -> None:
    c = console("audited")
    project = c.project()
    events = project.ledger.events()  # what the page lists (reads during rendering come later)
    html = c.get("/projects/console-demo").text
    assert "TASKLET" in html.upper()
    # nine phases, each with the time it completed and a one-line detail
    assert html.count('class="stage done"') == 9
    completed_at = {e.payload["phase"]: e.ts for e in project.ledger.events()
                    if e.type == "phase.completed"}
    assert completed_at["audit"][11:19] in html
    assert "сценариев" in html  # oracle detail
    assert "Пакет " in html  # release detail
    # KPIs
    for label in ["ПАРИТЕТ", "КРИТИЧНЫЕ", "СХОДСТВО КОДА", "LLM"]:
        assert label in html
    assert "1.000" in html
    assert "порог 0.05" in html
    # zones with artifact counts
    for zone in ["dirty", "released", "clean", "verifier"]:
        count = len(project.store.list(zone))
        assert re.search(rf'data-zone="{zone}"[^>]*>.*?<span class="zone-count">{count}</span>',
                         html, re.DOTALL), zone
    # ledger: latest first, short hashes, integrity ok
    assert events[-1].hash[:10] in html
    assert events[-1].hash not in html
    total = len(project.ledger.events())  # the first view logged its artifact reads
    with_artifacts = c.get("/projects/console-demo", params={"artifacts": "1"}).text
    assert f"Показаны последние 50 из {total}" in with_artifacts
    assert "project.created" not in with_artifacts
    full = c.get("/projects/console-demo", params={"all": "1"}).text
    assert full.index(events[-1].hash[:10]) < full.index("project.created")
    assert "цепочка цела" in html


def test_overview_ledger_filter_by_type_prefix(console) -> None:
    c = console("audited")
    html = c.get("/projects/console-demo", params={"type": "barrier."}).text
    rows = re.findall(r'<td class="event-type">([^<]+)</td>', html)
    assert rows and all(r.startswith("barrier.") for r in rows)
    assert {"barrier.prepared", "barrier.approved", "barrier.release"} <= set(rows)
    assert 'value="barrier."' in html


def test_overview_ledger_hides_artifact_events_by_default(console) -> None:
    c = console("audited")
    events = c.project().ledger.events()
    artifacts = sum(e.type.startswith("artifact.") for e in events)
    assert artifacts
    html = c.get("/projects/console-demo", params={"all": "1"}).text
    rows = re.findall(r'<td class="event-type">([^<]+)</td>', html)
    assert rows and not any(r.startswith("artifact.") for r in rows)
    assert "показать артефакты" in html
    assert f"Скрыто событий artifact.*: {artifacts}" in html
    with_artifacts = c.get("/projects/console-demo",
                           params={"all": "1", "artifacts": "1"}).text
    rows = re.findall(r'<td class="event-type">([^<]+)</td>', with_artifacts)
    assert any(r.startswith("artifact.") for r in rows)
    assert "скрыть артефакты" in with_artifacts
    # an explicit artifact. prefix shows them too
    only = c.get("/projects/console-demo", params={"type": "artifact."}).text
    rows = re.findall(r'<td class="event-type">([^<]+)</td>', only)
    assert rows and all(r.startswith("artifact.") for r in rows)


def test_overview_ledger_rows_carry_a_payload_summary(console) -> None:
    c = console("audited")
    html = c.get("/projects/console-demo", params={"all": "1", "artifacts": "1"}).text
    assert "СВОДКА" in html
    summaries = re.findall(r'<td class="event-summary[^"]*">([^<]*)</td>', html)
    assert "этап audit" in summaries
    assert "Пётр Петров · оператор платформы" in summaries
    assert any(s.startswith("analyst · ") and "$" in s for s in summaries)  # llm.call
    assert any(s.startswith("page:") for s in summaries)  # artifact.put: kind:name
    assert any("iteration=1" in s and "passed=" in s for s in summaries)  # counts
    assert all(len(s) <= 100 for s in summaries)


def test_overview_reports_a_broken_ledger(console) -> None:
    c = console("prepared")
    path = c.project().ledger.path
    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[1])
    event["actor"] = "tampered"
    lines[1] = json.dumps(event, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    html = c.get("/projects/console-demo").text
    assert "Целостность нарушена: запись 1" in html
    assert 'class="integrity broken"' in html


def test_overview_of_a_fresh_project(console) -> None:
    html = console("created").get("/projects/console-demo").text
    assert html.count('class="stage done"') == 1
    assert "Нет отчёта" in html  # parity KPI before parity
    assert "$0.0000" in html


def test_artifact_reads_are_logged_once_per_server_run(console) -> None:
    c = console("audited")
    c.get("/projects/console-demo")
    reads = [e for e in c.project().ledger.events() if e.type == "artifact.read"]
    for url in ["/projects/console-demo", "/projects/console-demo/release",
                "/projects/console-demo/parity", "/projects/console-demo"]:
        c.get(url)
    c.get("/projects/console-demo/release")
    after = [e for e in c.project().ledger.events() if e.type == "artifact.read"]
    ids = [e.payload["id"] for e in after[len(reads):]]
    assert len(ids) == len(set(ids))  # a repeated view reads nothing again
    assert all(e.payload["reader"] == "verifier" for e in after[len(reads):])
