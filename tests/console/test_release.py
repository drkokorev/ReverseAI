"""Release review and approval at the barrier."""

import re
import threading

import pytest

from reverseai import pipeline
from reverseai.barrier.release import PreparedRelease
from reverseai.console.roles import approval_role
from reverseai.pipeline import Phase, load_state
from reverseai.zones.store import Zone

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


@pytest.fixture
def console_lang() -> str:
    return "ru"


URL = "/projects/console-demo/release"


def _draft(project) -> PreparedRelease:
    ref = load_state(project).refs["release_draft"]
    return PreparedRelease.model_validate(project.store.get_json(ref, Zone.VERIFIER))


def _approve(c, **over):
    sha = pipeline.draft_sha256(c.project())
    form = {"approver": "Анна Аналитик", "role": "customer_analyst", "confirm": "on",
            "sha": sha, **over}
    return c.post(f"{URL}/approve", {k: v for k, v in form.items() if v is not None})


def test_release_page_shows_spec_scenarios_cleanup_and_hash(console) -> None:
    c = console("prepared")
    draft = _draft(c.project())
    html = c.get(URL).text
    assert draft.package_sha256 in html
    # tabs
    for label in ["СПЕЦИФИКАЦИЯ", f"СЦЕНАРИИ · {len(draft.scenarios)}", "ОЧИСТКА"]:
        assert label in html
    # spec sections
    assert draft.spec.features[0].id in html
    assert draft.spec.features[0].title in html
    assert f"ФУНКЦИИ · {len(draft.spec.features)}" in html
    for heading in ["ПРАВИЛА", "СУЩНОСТИ", "API", "ПРОБЕЛЫ"]:
        assert heading in html
    # scenarios: method, path, expectations, critical flag
    scenario = draft.scenarios[0]
    step = scenario.steps[0]
    assert scenario.id in html
    assert f"{step.step.method} {step.step.path}" in html
    assert f"→ {step.expect.status}" in html
    assert ("критичный" in html) == any(s.critical for s in draft.scenarios)
    # cleanup tab
    for label in ["НАХОДКИ", "УДЕРЖАНО", "ОТБРОШЕНО ОРАКУЛОМ"]:
        assert label in html
    # approval form: both roles, confirmation checkbox, the hash being signed
    assert 'value="operator"' in html and 'value="customer_analyst"' in html
    assert "Оператор платформы" in html and "Аналитик заказчика" in html
    assert 'name="confirm"' in html
    assert f'name="sha" value="{draft.package_sha256}"' in html
    assert "Юрист заказчика получает итоговый пакет доказательств после аудита." in html


@pytest.mark.parametrize("tab", ["spec", "scenarios", "cleanup"])
def test_tabs_work_without_javascript(console, tab) -> None:
    html = console("prepared").get(URL, params={"tab": tab}).text
    panels = dict(re.findall(r'<div class="tab-panel" id="tab-(\w+)"( hidden)?', html))
    assert set(panels) == {"spec", "scenarios", "cleanup"}
    assert panels[tab] == ""
    assert all(hidden == " hidden" for name, hidden in panels.items() if name != tab)
    assert f'href="?tab={tab}" role="tab" aria-selected="true"' in html


def test_cleanup_tab_lists_findings_withheld_values_and_dropped_scenarios(console) -> None:
    c = console("prepared")
    project = c.project()
    draft = _draft(project)
    html = c.get(URL, params={"tab": "cleanup"}).text
    findings = len(draft.report.findings)
    assert re.search(rf'data-stat="findings"[^>]*>\s*{findings}<', html)
    for finding in draft.report.findings:
        assert finding.location in html
    if not draft.report.findings:
        assert "Санитайзер ничего не нашёл" in html


def test_body_warnings_are_labelled_and_counted_apart_from_findings(console) -> None:
    from reverseai.barrier.sanitizer import WARNING_KINDS, Finding

    c = console("prepared")
    project = c.project()
    draft = _draft(project)
    assert not [f for f in draft.report.findings if f.kind in WARNING_KINDS]
    blocking = len(draft.report.findings)
    warning = Finding(kind="body_warning", location="scenario S-001 step 1 body /title",
                      excerpt="verbatim: some sentence from the original page")
    draft.report.findings.append(warning)
    ref = project.store.put_json(Zone.DIRTY, "release_draft", "release_draft",
                                 draft.model_dump(mode="json"))
    state = load_state(project)
    state.refs["release_draft"] = ref.id
    pipeline.save_state(project, state)

    html = c.get(URL, params={"tab": "cleanup"}).text
    assert re.search(rf'data-stat="findings"[^>]*>\s*{blocking}<', html)
    assert re.search(r'data-stat="warnings"[^>]*>\s*1<', html)
    assert "ПРЕДУПРЕЖДЕНИЯ" in html
    assert "предупреждение (тело запроса)" in html
    assert ">body_warning<" not in html
    assert warning.location in html and "some sentence from the original page" in html


def test_release_page_before_prepare_release(console) -> None:
    html = console("specced").get(URL).text
    assert "Черновик выпуска ещё не подготовлен" in html
    assert 'name="approver"' not in html


def test_approve_releases_the_draft(console) -> None:
    c = console("prepared")
    sha = pipeline.draft_sha256(c.project())
    r = _approve(c)
    assert r.status_code == 303 and r.headers["location"] == URL
    events = [e.type for e in c.project().ledger.events()]
    assert events[-3:] == ["barrier.approved", "barrier.release", "phase.completed"]
    state = load_state(c.project())
    assert Phase.RELEASE in state.completed
    package = c.project().store.get_json(state.refs["release"], Zone.VERIFIER)
    approval = package["approval"]
    assert approval["approver"] == "Анна Аналитик"
    assert approval["role"] == approval_role("customer_analyst")
    assert approval["package_sha256"] == sha

    html = c.get(URL).text
    assert "ВЫПУЩЕНО" in html
    assert "Анна Аналитик" in html
    assert "аналитик заказчика" in html
    assert approval["approved_at"][:10] in html
    assert 'name="approver"' not in html  # no second approval form
    assert 'href="/projects/console-demo/parity"' in html


def test_approve_with_a_stale_hash_is_rejected(console) -> None:
    c = console("prepared")
    r = _approve(c, sha="0" * 64)
    assert r.status_code == 409
    assert "черновик изменился — обновите страницу и проверьте пакет заново" in r.text
    assert "approval does not match" not in r.text
    assert Phase.RELEASE not in load_state(c.project()).completed
    types = [e.type for e in c.project().ledger.events()]
    assert "barrier.rejected" in types and "barrier.release" not in types[-10:]


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"confirm": None}, "Подтвердите, что просмотрели пакет"),
        ({"approver": "  "}, "Укажите, кто согласует пакет"),
        ({"role": "customer_lawyer"}, "Неизвестная роль"),
    ],
)
def test_approve_form_is_validated(console, over, message) -> None:
    c = console("prepared")
    before = len(c.project().ledger.events())
    r = _approve(c, **over)
    assert r.status_code == 400
    assert message in r.text
    added = {e.type for e in c.project().ledger.events()[before:]}
    assert added <= {"artifact.read"}  # only the page's own (logged) reads


def test_approve_before_prepare_release_is_refused(console) -> None:
    c = console("specced")
    r = c.post(f"{URL}/approve", {"approver": "A", "role": "operator", "confirm": "on",
                                  "sha": "0" * 64})
    assert r.status_code == 409
    assert "сначала завершите этап «Подготовка выпуска» (prepare_release)" in r.text


def test_approve_while_a_job_runs_is_refused(console) -> None:
    gate = threading.Event()
    c = console("prepared")
    c.ctx.jobs.start("console-demo", "audit", "Аудит", lambda log: gate.wait(10) and None)
    r = _approve(c)
    assert r.status_code == 409
    assert "Дождитесь завершения задачи «Аудит»" in r.text
    gate.set()
    c.wait()
    assert Phase.RELEASE not in load_state(c.project()).completed
