import json
from pathlib import Path

import pytest

from reverseai.barrier.release import (
    Approval,
    PreparedRelease,
    ReleaseError,
    package_sha256,
    prepare_release,
    release,
)
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.project import Attestation, Mode, Project, ProjectCard, create_project
from reverseai.spec.model import ApiContract, BehaviorSpec, Evidence, SpecItem
from reverseai.zones.store import Zone

APP_JS = (
    Path(__file__).resolve().parents[2] / "bench/targets/taskboard/static/app.js"
).read_text(encoding="utf-8")
JS_SLICE = "That title is too long (200 characters max)"
PAGE_TEXT = "Welcome to the shared board where your whole team plans the week together"
FORM_LABEL = "Describe what needs doing so that everyone on the team understands"
SERVER_MESSAGE = "Your workspace has reached the maximum number of open tasks allowed"
BRAND_COPY = "Plan your whole week with TaskBoard Pro every day"


@pytest.fixture
def project(tmp_path) -> Project:
    card = ProjectCard(
        name="Barrier Demo",
        mode=Mode.LEGACY,
        target_base_url="https://app.example.com/",
        allowed_domains=["app.example.com", "cdn.example.net"],
        attestation=Attestation(
            lawful_access=True, basis="own contract", signed_by="Ivan",
            signed_at="2026-10-20T10:00:00Z",
        ),
        brand_terms=["TaskBoard Pro", "TaskBoard"],
        product_name="Tasklet",
    )
    project = create_project(card, tmp_path)
    store = project.store
    store.put(Zone.DIRTY, "expression", "https://app.example.com/static/app.js",
              APP_JS.encode("utf-8"))
    store.put_json(Zone.DIRTY, "page", "https://app.example.com/", {
        "url": "https://app.example.com/", "title": "TaskBoard Pro", "links": [],
        "forms": [{"action": "/api/tasks", "method": "post", "fields": [
            {"name": "title", "type": "text", "required": True, "label": FORM_LABEL},
        ]}],
        "buttons": ["Add"], "text_excerpt": PAGE_TEXT, "screenshot_ref": None,
    })
    store.put_json(Zone.DIRTY, "har", "https://app.example.com/", _har(
        ("https://app.example.com/api/tasks",
         {"error": {"code": "limit", "detail": [SERVER_MESSAGE]}}),
        ("https://cdn.example.net/static/hero.js", None),
    ))
    store.put(Zone.DIRTY, "document", "https://app.example.com/about",
              f"<p>{BRAND_COPY}</p>".encode())
    return project


def _har(*entries: tuple[str, object]) -> dict:
    def entry(url: str, body: object) -> dict:
        text = json.dumps(body) if body is not None else "var x = 1;"
        mime = "application/json" if body is not None else "application/javascript"
        return {
            "request": {"method": "GET", "url": url, "headers": []},
            "response": {
                "status": 200,
                "headers": [{"name": "Content-Type", "value": mime}],
                "content": {"size": len(text), "mimeType": mime, "text": text},
            },
        }

    return {"log": {"version": "1.2", "entries": [entry(u, b) for u, b in entries]}}


def _spec(**over) -> BehaviorSpec:
    return BehaviorSpec(
        product_name="Tasklet",
        summary="TaskBoard Pro hosted at app.example.com keeps team tasks.",
        features=[
            SpecItem(
                id="F-001",
                title="Create task",
                description=f"Rejects long titles with: {JS_SLICE}",
                confidence="high",
                evidence=[Evidence(kind="page", ref="https://cdn.example.net/x.js")],
            ),
            SpecItem(
                id="F-002",
                title="Landing",
                description=f"Home page says {PAGE_TEXT}",
                confidence="low",
                evidence=[],
            ),
        ],
        entities=[],
        rules=[],
        api=[],
        gaps=[],
    ).model_copy(update=over)


def _scenarios() -> list[Scenario]:
    return [
        Scenario(
            id="S-001",
            title="Create",
            source_exchanges=["ex1"],
            steps=[
                ScenarioStep(
                    step=Step(method="POST", path="/api/tasks", json_body={"title": "A"}),
                    expect=Expect(status=201, json_equals={"/title": "A", "/msg": JS_SLICE}),
                )
            ],
        )
    ]


def _draft(project: Project, ref_id: str) -> PreparedRelease:
    return PreparedRelease.model_validate(project.store.get_json(ref_id, Zone.DIRTY))


def _approval(sha: str) -> Approval:
    return Approval(
        approver="Petrov", role="customer_analyst", approved_at="2026-10-21T09:00:00Z",
        package_sha256=sha,
    )


def test_prepare_release_stores_sanitized_draft_and_markdown(project):
    ref = prepare_release(project, _spec(), _scenarios())
    assert ref.zone == Zone.DIRTY
    assert ref.kind == "release_draft"
    draft = _draft(project, ref.id)
    assert draft.spec_sha256 == draft.spec.sha256()
    assert draft.spec.summary == "Tasklet hosted at <original> keeps team tasks."
    assert draft.spec.features[0].description == "Rejects long titles with: [removed: verbatim]"
    assert draft.spec.features[0].evidence[0].ref == "<original>"
    assert draft.spec.features[1].description == "Home page says [removed: verbatim]"
    assert draft.scenarios[0].steps[0].expect.json_equals == {"/title": "A"}
    assert draft.scenarios[0].source_exchanges == []
    kinds = {f.kind for f in draft.report.findings}
    assert kinds == {"brand", "url", "verbatim"}
    [md_ref] = project.store.list(Zone.DIRTY, "release_draft_md")
    md = project.store.get(md_ref.id, Zone.DIRTY).decode("utf-8")
    assert "# Tasklet" in md
    assert "[removed: verbatim]" in md


@pytest.mark.parametrize("quoted", [SERVER_MESSAGE, FORM_LABEL, BRAND_COPY])
def test_prepare_release_indexes_har_messages_labels_and_branded_copy(project, quoted):
    spec = _spec(gaps=[f"Quote: {quoted}"])
    ref = prepare_release(project, spec, [])
    assert _draft(project, ref.id).spec.gaps == ["Quote: [removed: verbatim]"]


PROBE_MESSAGE = "Titles must be unique among the open tasks of this workspace board"


def test_prepare_release_indexes_pipeline_exchange_messages(project):
    project.store.put_json(Zone.DIRTY, "exchanges", "exchanges", [
        {"id": "p0", "response_json": {"error": "invalid", "detail": PROBE_MESSAGE}},
        {"id": "p1", "response_json": None},
    ])
    ref = prepare_release(project, _spec(gaps=[f"Quote: {PROBE_MESSAGE}"]), [])
    assert _draft(project, ref.id).spec.gaps == ["Quote: [removed: verbatim]"]


def test_prepare_release_requires_project_product_name(project):
    with pytest.raises(ReleaseError):
        prepare_release(project, _spec(product_name="Other"), [])


def test_draft_with_removed_span_across_newline_releases(project):
    project.store.put(Zone.DIRTY, "expression", "https://app.example.com/b.js",
                      b"the board alpha beta gamma delta epsilon zeta eta theta")
    gap = "Users can return to the board alpha beta gamma delta\nepsilon zeta eta theta then save; done"
    ref = prepare_release(project, _spec(gaps=[gap]), [])
    draft = _draft(project, ref.id)
    assert draft.spec.gaps == ["Users can return to [removed: verbatim]\n then save; done"]
    out = release(project, ref.id, _approval(draft.package_sha256))
    assert out.zone == Zone.RELEASED


def test_release_rejects_hash_mismatch(project):
    ref = prepare_release(project, _spec(), _scenarios())
    with pytest.raises(ReleaseError):
        release(project, ref.id, _approval("0" * 64))
    assert project.store.list(Zone.RELEASED) == []
    types = [e.type for e in project.ledger.events()]
    assert "barrier.release" not in types
    assert "barrier.approved" not in types


def test_release_rejects_draft_that_is_not_clean(project):
    dirty = _spec()
    draft = PreparedRelease(
        spec=dirty, scenarios=[], report={"findings": []}, spec_sha256=dirty.sha256(),
        package_sha256=package_sha256(dirty, []),
    )
    ref = project.store.put_json(
        Zone.DIRTY, "release_draft", "forged", draft.model_dump(mode="json")
    )
    with pytest.raises(ReleaseError):
        release(project, ref.id, _approval(package_sha256(dirty, [])))
    assert project.store.list(Zone.RELEASED) == []


def test_release_rejects_scenario_values_that_are_not_clean(project):
    ref = prepare_release(project, _spec(), [])
    draft = _draft(project, ref.id)
    sha = package_sha256(draft.spec, _scenarios())
    forged = draft.model_copy(update={"scenarios": _scenarios(), "package_sha256": sha})
    forged_ref = project.store.put_json(
        Zone.DIRTY, "release_draft", "forged", forged.model_dump(mode="json")
    )
    with pytest.raises(ReleaseError, match="not clean|sanitizer would drop"):
        release(project, forged_ref.id, _approval(sha))
    assert "barrier.rejected" in [e.type for e in project.ledger.events()]


def test_release_rejects_foreign_product_name(project):
    ref = prepare_release(project, _spec(), [])
    draft = _draft(project, ref.id)
    spec = draft.spec.model_copy(update={"product_name": "Other"})
    forged = PreparedRelease(
        spec=spec, scenarios=[], report=draft.report, spec_sha256=spec.sha256(),
        package_sha256=package_sha256(spec, []),
    )
    forged_ref = project.store.put_json(
        Zone.DIRTY, "release_draft", "forged", forged.model_dump(mode="json")
    )
    with pytest.raises(ReleaseError):
        release(project, forged_ref.id, _approval(package_sha256(spec, [])))


def test_release_rejects_corrupted_draft(project):
    ref = prepare_release(project, _spec(), [])
    draft = _draft(project, ref.id)
    (project.dir / "artifacts" / "dirty" / ref.id).write_bytes(b"{}")
    with pytest.raises(ReleaseError):
        release(project, ref.id, _approval(draft.package_sha256))
    assert "barrier.rejected" in [e.type for e in project.ledger.events()]
    assert project.store.list(Zone.RELEASED) == []


def test_release_rejects_non_draft_artifact(project):
    [page] = project.store.list(Zone.DIRTY, "page")
    with pytest.raises(ReleaseError):
        release(project, page.id, _approval("0" * 64))


def test_release_writes_released_zone_and_ledger(project):
    ref = prepare_release(project, _spec(), _scenarios())
    draft = _draft(project, ref.id)
    out = release(project, ref.id, _approval(draft.package_sha256))
    assert out.zone == Zone.RELEASED
    assert out.kind == "release_package"
    package = project.store.get_json(out.id, Zone.CLEAN)
    assert set(package) == {"spec", "scenarios", "approval", "sanitize_report"}
    assert BehaviorSpec.model_validate(package["spec"]).sha256() == draft.spec_sha256
    assert package["approval"]["approver"] == "Petrov"
    assert len(package["scenarios"]) == 1
    assert package["sanitize_report"]["findings"]
    assert all(f["excerpt"] == "" for f in package["sanitize_report"]["findings"])
    blob = json.dumps(package).lower()
    for leaked in ("taskboard", "example.com", "example.net", "too long", "welcome to"):
        assert leaked not in blob
    events = {e.type: e for e in project.ledger.events()}
    assert events["barrier.approved"].payload == {
        "approver": "Petrov", "role": "customer_analyst",
        "approved_at": "2026-10-21T09:00:00Z", "package_sha256": draft.package_sha256,
    }
    assert events["barrier.release"].payload == {
        "ref": out.id, "spec_sha256": draft.spec_sha256,
        "package_sha256": draft.package_sha256, "scenarios": 1,
    }
    assert project.ledger.verify().ok
    order = [
        e.type for e in project.ledger.events()
        if e.type in ("barrier.approved", "barrier.release")
        or (e.type == "artifact.put" and e.payload["kind"] == "release_package")
    ]
    assert order == ["artifact.put", "barrier.approved", "barrier.release"]


# --- final review fixes --------------------------------------------------------------------


def _branded_scenarios() -> list[Scenario]:
    return [
        Scenario(id="S-001", title="Create", steps=[
            ScenarioStep(
                step=Step(method="POST", path="/api/taskboard/tasks",
                          json_body={"title": "A", "source": "app.example.com"}),
                expect=Expect(status=201, json_shape={"type": "object"},
                              json_equals={"/title": "A", "/msg": SERVER_MESSAGE}),
            ),
        ]),
    ]


@pytest.mark.usefixtures("lang_ru")  # checks the Russian copy
def test_review_markdown_shows_released_scenarios_and_withheld_pointers(project):
    ref = prepare_release(project, _spec(), _branded_scenarios())
    draft = _draft(project, ref.id)
    step = draft.scenarios[0].steps[0]
    assert step.step.path == "/api/tasklet/tasks"
    assert step.step.json_body == {"title": "A", "source": "<original>"}
    assert step.expect.json_equals == {"/title": "A"}
    [md_ref] = project.store.list(Zone.DIRTY, "release_draft_md")
    md = project.store.get(md_ref.id, Zone.DIRTY).decode("utf-8")
    assert "## Сценарии" in md
    assert "S-001" in md and "`POST /api/tasklet/tasks`" in md
    assert '{"title": "A", "source": "<original>"}' in md
    assert "статус 201" in md and '`/title` = "A"' in md
    assert "## Удалённые ожидаемые значения" in md
    assert "S-001, шаг 1: `/msg`" in md
    assert SERVER_MESSAGE not in md.split("## Удалённые ожидаемые значения")[1]
    assert "taskboard" not in md.lower().split("## отчёт санитайзера")[0]


def test_masked_paths_and_bodies_release_cleanly(project):
    ref = prepare_release(project, _spec(), _branded_scenarios())
    draft = _draft(project, ref.id)
    locations = {f.location for f in draft.report.findings}
    assert {"scenarios[S-001].steps[0].path", "scenarios[S-001].steps[0].json_body"} <= locations
    out = release(project, ref.id, _approval(draft.package_sha256))
    blob = json.dumps(project.store.get_json(out.id, Zone.CLEAN)).lower()
    assert "taskboard" not in blob and "example.com" not in blob


def test_approval_binds_the_scenarios_too(project):
    first = prepare_release(project, _spec(), _scenarios())
    old = _draft(project, first.id)
    other = _scenarios()
    other[0].steps[0].expect.status = 400
    second = prepare_release(project, _spec(), other)
    new = _draft(project, second.id)
    assert new.spec_sha256 == old.spec_sha256
    assert new.package_sha256 != old.package_sha256
    assert new.package_sha256 == package_sha256(new.spec, new.scenarios)
    with pytest.raises(ReleaseError, match="package"):
        release(project, second.id, _approval(old.package_sha256))
    assert project.store.list(Zone.RELEASED) == []
    out = release(project, second.id, _approval(new.package_sha256))
    assert project.store.get_json(out.id, Zone.CLEAN)["scenarios"][0]["steps"][0]["expect"][
        "status"] == 400


def test_release_rejects_scenarios_swapped_after_hashing(project):
    ref = prepare_release(project, _spec(), _scenarios())
    draft = _draft(project, ref.id)
    swapped = [s.model_copy(deep=True) for s in draft.scenarios]
    swapped[0].steps[0].expect.status = 500
    forged = draft.model_copy(update={"scenarios": swapped})
    forged_ref = project.store.put_json(
        Zone.DIRTY, "release_draft", "forged", forged.model_dump(mode="json")
    )
    with pytest.raises(ReleaseError, match="package"):
        release(project, forged_ref.id, _approval(draft.package_sha256))


def test_long_path_seen_in_the_original_survives_release_unchanged(project):
    next_link = "/api/tasks?page=2&per_page=20&sort=created"
    project.store.put(Zone.DIRTY, "document", "https://app.example.com/board",
                      f'<a href="{next_link}">Next</a>'.encode())
    project.store.put_json(Zone.DIRTY, "exchanges", "exchanges", [
        {"response_json": {"next": next_link, "items": []}},
    ])
    spec = _spec(api=[ApiContract(method="GET", path=next_link, request_schema=None,
                                  responses={}, description="Lists tasks page by page.")])
    scenarios = [Scenario(id="S-001", title="Page two", steps=[ScenarioStep(
        step=Step(method="GET", path=next_link), expect=Expect(status=200),
    )])]
    ref = prepare_release(project, spec, scenarios)
    draft = _draft(project, ref.id)
    assert draft.spec.api[0].path == next_link
    assert draft.scenarios[0].steps[0].step.path == next_link
    out = release(project, ref.id, _approval(draft.package_sha256))
    package = project.store.get_json(out.id, Zone.CLEAN)
    assert package["spec"]["api"][0]["path"] == next_link
    assert package["scenarios"][0]["steps"][0]["step"]["path"] == next_link


@pytest.mark.usefixtures("lang_ru")  # checks the Russian copy
def test_renamed_keys_agree_across_spec_and_scenarios_and_release(project):
    schema = {"type": "object", "properties": {"TaskBoard": {"type": "string"},
                                               "Tasklet": {"type": "integer"}},
              "required": ["TaskBoard"]}
    spec = _spec(api=[ApiContract(method="POST", path="/api/tasks", request_schema=schema,
                                  responses={201: schema}, description="Creates a task.")])
    scenarios = [Scenario(id="S-001", title="Create", steps=[ScenarioStep(
        step=Step(method="POST", path="/api/tasks", json_body={"TaskBoard": "A"}),
        expect=Expect(status=201, json_shape={"type": "object", "properties": {
            "TaskBoard": {"type": "string"}}}, json_equals={"/TaskBoard": "A"}),
    )])]  # the scenarios alone never name "Tasklet": only the package-wide renames agree
    ref = prepare_release(project, spec, scenarios)
    draft = _draft(project, ref.id)
    [name] = draft.scenarios[0].steps[0].step.json_body
    assert name.startswith("Tasklet_")
    assert name in draft.spec.api[0].request_schema["properties"]
    assert draft.spec.api[0].request_schema["required"] == [name]
    assert name in draft.spec.api[0].responses[201]["properties"]
    assert name in draft.scenarios[0].steps[0].expect.json_shape["properties"]
    assert draft.scenarios[0].steps[0].expect.json_equals == {f"/{name}": "A"}
    md = project.store.get(
        project.store.list(Zone.DIRTY, "release_draft_md")[0].id, Zone.DIRTY
    ).decode("utf-8")
    assert "S-001, шаг 1" not in md  # a renamed pointer is not a withheld value
    out = release(project, ref.id, _approval(draft.package_sha256))
    blob = json.dumps(project.store.get_json(out.id, Zone.CLEAN)).lower()
    assert "taskboard" not in blob


@pytest.mark.usefixtures("lang_ru")  # checks the Russian copy
def test_body_values_seen_in_the_original_warn_but_release(project):
    scenarios = [Scenario(id="S-001", title="Create", steps=[ScenarioStep(
        step=Step(method="POST", path="/api/tasks",
                  json_body={"title": JS_SLICE, "script": "x => { return 1; }"}),
        expect=Expect(status=201),
    )])]
    ref = prepare_release(project, _spec(), scenarios)
    draft = _draft(project, ref.id)
    assert draft.scenarios[0].steps[0].step.json_body == {
        "title": JS_SLICE, "script": "x => { return 1; }"
    }
    warnings = [f for f in draft.report.findings if f.kind == "body_warning"]
    assert {f.location for f in warnings} == {"scenarios[S-001].steps[0].json_body"}
    assert len(warnings) == 2
    md = project.store.get(
        project.store.list(Zone.DIRTY, "release_draft_md")[0].id, Zone.DIRTY
    ).decode("utf-8")
    assert "## Предупреждения" in md
    assert "предупреждение (тело запроса) — scenarios[S-001].steps[0].json_body" in md
    out = release(project, ref.id, _approval(draft.package_sha256))
    package = project.store.get_json(out.id, Zone.CLEAN)
    kinds = [f["kind"] for f in package["sanitize_report"]["findings"]]
    assert kinds.count("body_warning") == 2


def test_review_markdown_is_english_by_default(project):
    scenarios = _branded_scenarios()
    scenarios[0].critical = True
    prepare_release(project, _spec(), scenarios)
    [md_ref] = project.store.list(Zone.DIRTY, "release_draft_md")
    md = project.store.get(md_ref.id, Zone.DIRTY).decode("utf-8")
    assert md.startswith("# Tasklet — behavioral spec v1\n")
    for heading in ("## Overview", "## Features", "## Scenarios", "## Withheld expected values",
                    "## Sanitizer report"):
        assert heading in md, heading
    assert "### S-001: Create (critical)" in md
    assert "→ status 201" in md and "   - shape: `" in md
    assert "S-001, step 1: `/msg`" in md
    assert "Package SHA-256 (spec + scenarios): `" in md
    assert "Scenarios: 1" in md
    assert "- brand — scenarios[S-001].steps[0].path" in md


def test_release_error_reason_in_the_ledger_is_english_in_any_language(project, lang_ru):
    ref = prepare_release(project, _spec(), _branded_scenarios())
    with pytest.raises(ReleaseError, match="согласование не совпадает"):
        release(project, ref.id, _approval("0" * 64))
    [event] = [e for e in project.ledger.events() if e.type == "barrier.rejected"]
    assert event.payload["reason"] == "approval does not match the draft package hash"
