from pathlib import Path

from reverseai.barrier.sanitizer import (
    ExpressionIndex,
    build_expression_index,
    release_scenarios,
    sanitize_spec,
    sanitize_text,
    tokenize,
)
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.spec.model import ApiContract, BehaviorSpec, Entity, Evidence, SpecItem

APP_JS = (
    Path(__file__).resolve().parents[2] / "bench/targets/taskboard/static/app.js"
).read_text(encoding="utf-8")
BRANDS = ["TaskBoard Pro", "TaskBoard"]
DOMAINS = ["app.example.com"]
# 10 consecutive tokens of a UI message string in app.js
JS_SLICE = "That title is too long (200 characters max)"


def _index() -> ExpressionIndex:
    return build_expression_index([APP_JS])


def _clean(text: str, index: ExpressionIndex | None = None):
    return sanitize_text(
        text,
        location="x",
        index=index or _index(),
        brand_terms=BRANDS,
        product_name="Tasklet",
        target_domains=DOMAINS,
    )


def test_tokenize_lowercases_and_splits_punctuation():
    assert tokenize("Foo(bar, 2)") == ["foo", "(", "bar", ",", "2", ")"]


def test_index_merges_consecutive_shingles_into_one_span():
    index = build_expression_index(["a b c d e f g h i j k"], shingle=4)
    tokens = tokenize("x a b c d e f y c d e f")
    assert index.contains_span(tokens) == [(1, 7), (8, 12)]
    assert index.contains_span(tokenize("a b c")) == []


def test_removes_verbatim_js():
    slice_tokens = tokenize(JS_SLICE)
    js_tokens = tokenize(APP_JS)
    assert len(slice_tokens) >= 8
    assert any(
        js_tokens[i : i + len(slice_tokens)] == slice_tokens for i in range(len(js_tokens))
    )
    text = f"Long titles are rejected. The form shows: {JS_SLICE}. Then it stops"
    out, findings = _clean(text)
    # the sentence period that follows the string in app.js is part of the copied span
    assert out == "Long titles are rejected. The form shows: [removed: verbatim] Then it stops"
    assert [f.kind for f in findings] == ["verbatim"]
    assert findings[0].location == "x"
    assert "too long" in findings[0].excerpt


def test_verbatim_respects_original_casing_and_spacing():
    out, findings = _clean("Shows THAT title   is too long ( 200 characters max ) here")
    assert out == "Shows [removed: verbatim] here"
    assert [f.kind for f in findings] == ["verbatim"]


def test_removes_code_pattern():
    text = "Adds a task. It calls const x = load(). Then renders\nfetch(u).then(r => r.json())\nok"
    out, findings = _clean(text, build_expression_index([]))
    assert out == "Adds a task. [removed: code]. Then renders\n[removed: code]\nok"
    assert [f.kind for f in findings] == ["code", "code"]


def test_code_patterns_each_trigger():
    index = build_expression_index([])
    for snippet in ("function (a)", "a => b", "let y = 2", "return a;", "obj = { }"):
        out, findings = _clean(f"Good sentence. Bad {snippet} here", index)
        assert out == "Good sentence. [removed: code]", snippet
        assert findings[0].kind == "code"


def test_replaces_brand_and_domain():
    out, findings = _clean("TaskBoard Pro at app.example.com")
    assert out == "Tasklet at <original>"
    assert sorted(f.kind for f in findings) == ["brand", "url"]


def test_replaces_full_urls_and_whole_brand_terms_only():
    out, _ = _clean(
        "See https://app.example.com/tasks?x=1, api.app.example.com and taskboard; "
        "TaskBoarding stays."
    )
    assert out == "See <original>, <original> and Tasklet; TaskBoarding stays."


def test_sanitized_text_is_stable_on_rerun():
    out, _ = _clean(
        f"TaskBoard Pro at app.example.com says {JS_SLICE}. It does let a = 1 too"
    )
    again, findings = _clean(out)
    assert findings == []
    assert again == out


def _spec() -> BehaviorSpec:
    return BehaviorSpec(
        product_name="Tasklet",
        summary="TaskBoard Pro keeps tasks.",
        features=[
            SpecItem(
                id="F-001",
                title="Create tasks in TaskBoard",
                description=f"Rejects long titles: {JS_SLICE}",
                confidence="high",
                evidence=[
                    Evidence(kind="page", ref="https://app.example.com/"),
                    Evidence(kind="endpoint", ref="POST /api/tasks"),
                ],
            )
        ],
        entities=[
            Entity(
                name="Task",
                fields={"taskboard": "string", "id": "integer"},
                description="One TaskBoard item.",
            )
        ],
        rules=[],
        api=[
            ApiContract(
                method="GET",
                path="/api/taskboard/{id}",
                request_schema={"taskboard": "string"},
                responses={200: {"taskboard": "string"}},
                description="Reads one item from app.example.com.",
            )
        ],
        gaps=["Unknown TaskBoard limits"],
    )


def test_sanitize_spec_cleans_prose_fields():
    spec = _spec()
    clean, report = sanitize_spec(spec, _index(), brand_terms=BRANDS, target_domains=DOMAINS)
    assert clean.summary == "Tasklet keeps tasks."
    assert clean.features[0].title == "Create tasks in Tasklet"
    assert clean.features[0].description == "Rejects long titles: [removed: verbatim]"
    assert clean.features[0].evidence[0].ref == "<original>"
    assert clean.features[0].evidence[1].ref == "POST /api/tasks"
    assert clean.entities[0].description == "One Tasklet item."
    assert clean.api[0].description == "Reads one item from <original>."
    assert clean.gaps == ["Unknown Tasklet limits"]
    locations = {f.location for f in report.findings}
    assert {"summary", "features[0].description", "features[0].evidence[0].ref"} <= locations


def test_identifiers_are_masked_but_schemas_untouched():
    spec = _spec()
    clean, report = sanitize_spec(spec, _index(), brand_terms=BRANDS, target_domains=DOMAINS)
    assert clean.features[0].id == "F-001"
    assert clean.entities[0].fields == {"Tasklet": "string", "id": "integer"}
    assert clean.api[0].method == "GET"
    assert clean.api[0].path == "/api/tasklet/{id}"
    locations = {f.location for f in report.findings}
    assert {"entities[0].fields.key", "api[0].path"} <= locations
    assert clean.api[0].request_schema == {"taskboard": "string"}
    assert clean.api[0].responses == {200: {"taskboard": "string"}}
    assert spec.summary == "TaskBoard Pro keeps tasks."  # input not mutated


def test_release_scenarios_drop_long_values():
    scenario = Scenario(
        id="S-001",
        title="Create a TaskBoard task",
        critical=True,
        source_exchanges=["abc123"],
        steps=[
            ScenarioStep(
                step=Step(method="POST", path="/api/tasks", json_body={"title": "Buy milk"}),
                expect=Expect(
                    status=201,
                    json_shape={"id": "integer", "title": "string"},
                    json_equals={
                        "/title": "Buy milk",
                        "/count": 3,
                        "/done": False,
                        "/note": None,
                        "/long": "x" * 65,
                        "/edge": "y" * 64,
                        "/obj": {"a": 1},
                        "/list": [1],
                        "/msg": JS_SLICE,
                        "/brand": "TaskBoard Pro",
                    },
                ),
            )
        ],
    )
    [out] = release_scenarios(
        [scenario], _index(), brand_terms=BRANDS, product_name="Tasklet",
        target_domains=DOMAINS,
    )
    expect = out.steps[0].expect
    assert expect.status == 201
    assert expect.json_shape == {"id": "integer", "title": "string"}
    assert expect.json_equals == {
        "/title": "Buy milk",
        "/count": 3,
        "/done": False,
        "/note": None,
        "/edge": "y" * 64,
    }
    assert out.source_exchanges == []
    assert out.critical is True
    assert out.title == "Create a Tasklet task"
    assert out.steps[0].step == scenario.steps[0].step
    assert scenario.source_exchanges == ["abc123"]  # input not mutated


def test_sanitizer_is_idempotent_when_a_removed_span_crosses_a_newline():
    index = build_expression_index(["the board alpha beta gamma delta epsilon zeta eta theta"])
    text = "Users can return to the board alpha beta gamma delta\nepsilon zeta eta theta then save; done"

    def run(t: str):
        return sanitize_text(
            t, location="x", index=index, brand_terms=BRANDS, product_name="Tasklet",
            target_domains=DOMAINS,
        )

    once, findings = run(text)
    assert [f.kind for f in findings] == ["verbatim"]
    assert once == "Users can return to [removed: verbatim]\n then save; done"
    twice, again = run(once)
    assert twice == once
    assert again == []


def test_brand_match_across_newline_keeps_the_line_break():
    index = build_expression_index([])
    out, findings = sanitize_text(
        "We return to TaskBoard\nPro then save; done", location="x", index=index,
        brand_terms=BRANDS, product_name="Tasklet", target_domains=DOMAINS,
    )
    assert out == "We return to Tasklet\n then save; done"
    assert [f.kind for f in findings] == ["brand"]
    assert sanitize_text(
        out, location="x", index=index, brand_terms=BRANDS, product_name="Tasklet",
        target_domains=DOMAINS,
    ) == (out, [])


# --- final review fixes --------------------------------------------------------------------

SERVER_PROSE = "A task with this title already exists"


def _releasable(value, request_values=frozenset()):
    from reverseai.barrier.sanitizer import releasable_value

    return releasable_value(
        value, request_values=request_values, index=_index(), brand_terms=BRANDS,
        product_name="Tasklet", target_domains=DOMAINS,
    )


def test_releasable_value_rule():
    assert _releasable(None) and _releasable(3) and _releasable(1.5) and _releasable(False)
    assert _releasable("duplicate") and _releasable("title_too_long")
    assert _releasable("/api/tasks/1") and _releasable("y" * 64)
    assert not _releasable("y" * 65)
    assert not _releasable(SERVER_PROSE)  # short server prose is not an identifier
    assert not _releasable("two words")
    assert _releasable("two words", {"two words"})  # echo of what the scenario sent
    assert not _releasable("TaskBoard", {"TaskBoard"})  # still has to be sanitizer-clean
    assert not _releasable({"a": 1}) and not _releasable([1])


def test_request_values_collects_bodies_and_paths():
    from reverseai.barrier.sanitizer import request_values

    scenario = Scenario(id="S", title="t", steps=[
        ScenarioStep(step=Step(method="POST", path="/api/tasks?tag=home%20chores",
                               json_body={"title": "Buy milk", "tags": ["a b"], "n": 2}),
                     expect=Expect(status=201)),
    ])
    values = request_values(scenario)
    assert {"Buy milk", "a b", "/api/tasks?tag=home%20chores", "home chores", "api",
            "tasks"} <= values


def test_release_scenarios_withhold_short_server_prose():
    scenario = Scenario(id="S-001", title="Duplicate", steps=[
        ScenarioStep(step=Step(method="POST", path="/api/tasks", json_body={"title": "Buy milk"}),
                     expect=Expect(status=409, json_equals={
                         "/message": SERVER_PROSE, "/error": "duplicate", "/title": "Buy milk",
                     })),
    ])
    [out] = release_scenarios([scenario], _index(), brand_terms=BRANDS, product_name="Tasklet",
                              target_domains=DOMAINS)
    assert out.steps[0].expect.json_equals == {"/error": "duplicate", "/title": "Buy milk"}


def test_releasable_value_accepts_a_trimmed_or_lowercased_echo():
    assert _releasable("Buy milk", {"  Buy milk  "})
    assert _releasable("buy milk", {"Buy  Milk"})
    assert not _releasable("Buy milk!", {"Buy milk"})


def test_every_spec_string_that_crosses_is_masked_or_reported():
    spec = BehaviorSpec(
        product_name="Tasklet", summary="s",
        features=[SpecItem(id="TaskBoard-1", title="t", description="d", confidence="high",
                           evidence=[])],
        entities=[Entity(name="Task", description="d",
                         fields={"app.example.com/ref": "TaskBoard id", "id": "integer"})],
        rules=[SpecItem(id="R:app.example.com", title="t", description="d", confidence="low",
                        evidence=[])],
        api=[ApiContract(method="GET", path="/api/items?src=app.example.com",
                         request_schema=None, responses={}, description="TaskBoard list")],
        gaps=[],
    )
    clean, report = sanitize_spec(spec, _index(), brand_terms=BRANDS, target_domains=DOMAINS)
    blob = clean.model_dump_json().lower()
    assert "taskboard" not in blob and "example.com" not in blob
    assert clean.features[0].id == "Tasklet-1"
    assert clean.rules[0].id == "R:<original>"
    assert clean.entities[0].fields == {"<original>": "Tasklet id", "id": "integer"}
    assert clean.api[0].path == "/api/items?src=original"
    assert {f.location for f in report.findings} >= {
        "features[0].id", "rules[0].id", "entities[0].fields.key",
        "entities[0].fields[<original>]", "api[0].path", "api[0].description",
    }
    again, report2 = sanitize_spec(clean, _index(), brand_terms=BRANDS, target_domains=DOMAINS)
    assert again == clean and report2.findings == []  # fixed point: release re-check agrees


def test_scenario_paths_and_bodies_are_masked_or_reported():
    from reverseai.barrier.sanitizer import sanitize_scenarios

    scenario = Scenario(id="S-001", title="Create", steps=[
        ScenarioStep(
            step=Step(method="POST", path="/api/taskboard/items?ref=app.example.com",
                      json_body={"TaskBoard": {"note": ["see https://app.example.com/x"]},
                                 "n": 1}),
            expect=Expect(status=201),
        ),
    ])
    [out], findings = sanitize_scenarios(
        [scenario], _index(), brand_terms=BRANDS, product_name="Tasklet", target_domains=DOMAINS,
    )
    step = out.steps[0].step
    assert step.path == "/api/tasklet/items?ref=original"
    assert step.json_body == {"Tasklet": {"note": ["see <original>"]}, "n": 1}
    assert {f.location for f in findings} == {
        "scenarios[S-001].steps[0].path", "scenarios[S-001].steps[0].json_body",
    }
    [again], findings2 = sanitize_scenarios(
        [out], _index(), brand_terms=BRANDS, product_name="Tasklet", target_domains=DOMAINS,
    )
    assert again == out and findings2 == []
    assert scenario.steps[0].step.path.startswith("/api/taskboard")  # input not mutated


# --- identifiers: identity masking only (N1, N2, N4, N5) -----------------------------------

LONG_PATHS = [
    "/api/tasks?page=2&per_page=20",
    "/projects/123/tasks/new",
    "/api/v1/tasks?status=open",
]
LONG_BODY = "x => { return a; } plus enough plain words to be eight tokens long"


def _identifier_index() -> ExpressionIndex:
    """The original's JS/HTML/responses, which contain the API paths and the body text."""
    return build_expression_index([
        APP_JS,
        '{"next": "/api/tasks?page=2&per_page=20"}',
        '<a href="/projects/123/tasks/new">New</a>',
        "fetch('/api/v1/tasks?status=open')",
        LONG_BODY,
    ])


def test_index_really_covers_the_long_paths():
    for path in LONG_PATHS:
        assert _clean(path, _identifier_index())[0] != path  # prose would lose it


def test_long_api_paths_present_in_the_original_survive_spec_sanitizing():
    spec = BehaviorSpec(
        product_name="Tasklet", summary="s", features=[], rules=[], gaps=[],
        entities=[Entity(name="Task", description="d", fields={"per_page": "integer"})],
        api=[ApiContract(method="GET", path=p, request_schema=None, responses={},
                         description="d") for p in LONG_PATHS],
    )
    clean, report = sanitize_spec(
        spec, _identifier_index(), brand_terms=BRANDS, target_domains=DOMAINS
    )
    assert [c.path for c in clean.api] == LONG_PATHS
    assert report.findings == []


def test_long_paths_and_body_strings_survive_scenario_sanitizing():
    from reverseai.barrier.sanitizer import sanitize_scenarios

    scenario = Scenario(id="S-001", title="List", steps=[
        ScenarioStep(step=Step(method="POST", path=p, json_body={"note": LONG_BODY}),
                     expect=Expect(status=200))
        for p in LONG_PATHS
    ])
    [out], findings = sanitize_scenarios(
        [scenario], _identifier_index(), brand_terms=BRANDS, product_name="Tasklet",
        target_domains=DOMAINS,
    )
    assert [s.step.path for s in out.steps] == LONG_PATHS
    # neither the verbatim nor the code pass touches request-body strings: they only warn
    assert all(s.step.json_body == {"note": LONG_BODY} for s in out.steps)
    assert {f.kind for f in findings} == {"body_warning"}
    assert {f.location for f in findings} == {
        f"scenarios[S-001].steps[{i}].json_body" for i in range(len(LONG_PATHS))
    }


def test_brand_and_domain_in_paths_become_url_safe():
    from reverseai.barrier.sanitizer import mask_identifier, path_slug

    out, findings = mask_identifier(
        "https://app.example.com:8443/api/TaskBoard/items?src=app.example.com&b=taskboard",
        location="p", brand_terms=BRANDS, product_name="My Clone 2", target_domains=DOMAINS,
        url_path=True,
    )
    assert out == "/api/my-clone-2/items?src=original&b=my-clone-2"
    assert {f.kind for f in findings} == {"url", "brand"}
    assert path_slug("Мой клон") == "product"  # nothing URL-safe left: neutral fallback
    again, findings2 = mask_identifier(
        out, location="p", brand_terms=BRANDS, product_name="My Clone 2",
        target_domains=DOMAINS, url_path=True,
    )
    assert again == out and findings2 == []


def test_field_names_that_mask_to_the_same_name_do_not_merge():
    spec = BehaviorSpec(
        product_name="Tasklet", summary="s", features=[], rules=[], api=[], gaps=[],
        entities=[Entity(name="Task", description="d", fields={
            "TaskBoard": "string", "Tasklet": "integer", "taskboard": "boolean",
        })],
    )
    clean, report = sanitize_spec(spec, _index(), brand_terms=BRANDS, target_domains=DOMAINS)
    assert clean.entities[0].fields == {
        "Tasklet_2": "string", "Tasklet": "integer", "Tasklet_3": "boolean",
    }
    assert [f.location for f in report.findings].count("entities[0].fields.key") == 2
    again, report2 = sanitize_spec(clean, _index(), brand_terms=BRANDS, target_domains=DOMAINS)
    assert again == clean and report2.findings == []


def test_body_keys_that_mask_to_the_same_name_do_not_merge():
    from reverseai.barrier.sanitizer import sanitize_scenarios

    scenario = Scenario(id="S-001", title="Create", steps=[ScenarioStep(
        step=Step(method="POST", path="/x", json_body={"TaskBoard": 1, "Tasklet": 2}),
        expect=Expect(status=201),
    )])
    [out], _ = sanitize_scenarios(
        [scenario], _index(), brand_terms=BRANDS, product_name="Tasklet", target_domains=DOMAINS,
    )
    assert out.steps[0].step.json_body == {"Tasklet_2": 1, "Tasklet": 2}


# --- audit 2026-10-22 ------------------------------------------------------------------------


def test_a_full_target_url_in_a_path_stays_an_absolute_path():
    from reverseai.barrier.sanitizer import mask_identifier

    for path, expected in [
        ("https://app.example.com/api/x", "/api/x"),
        ("https://app.example.com:8443/api/x?y=1", "/api/x?y=1"),
        ("//app.example.com/api/x", "/api/x"),
        ("https://app.example.com", "/"),
        ("/api/x?next=https://app.example.com/y", "/api/x?next=original/y"),
    ]:
        out, findings = mask_identifier(
            path, location="p", brand_terms=BRANDS, product_name="Tasklet",
            target_domains=DOMAINS, url_path=True,
        )
        assert out == expected, path
        assert [f.kind for f in findings] == ["url"]
        again, findings2 = mask_identifier(
            out, location="p", brand_terms=BRANDS, product_name="Tasklet",
            target_domains=DOMAINS, url_path=True,
        )
        assert again == out and findings2 == []


def _mask(text: str, brands: list[str], product: str = "OrderFlow", *, url_path: bool = False):
    from reverseai.barrier.sanitizer import mask_identifier

    return mask_identifier(
        text, location="k", brand_terms=brands, product_name=product,
        target_domains=DOMAINS, url_path=url_path,
    )


def test_brand_glued_inside_identifiers_is_masked():
    import re

    cases = [
        (["Acme"], "acme_id", False, "orderflow_id"),
        (["Acme"], "acmeId", False, "orderflowId"),
        (["Acme"], "AcmeTasks", False, "OrderFlowTasks"),
        (["Acme"], "myAcme", False, "myOrderFlow"),
        (["Acme"], "ACME_KEY", False, "ORDERFLOW_KEY"),
        (["Acme"], "Acme", False, "OrderFlow"),
        (["Task Board"], "TaskBoard", False, "OrderFlow"),
        (["Task Board"], "task_board_id", False, "orderflow_id"),
        (["Task Board"], "Task%20Board", False, "OrderFlow"),
        (["Acme"], "/api/acme_tasks", True, "/api/orderflow_tasks"),
        (["Acme"], "/api/acmeTasks/{v0}", True, "/api/orderflowTasks/{v0}"),
        (["Task Board"], "/api/task-board/x", True, "/api/orderflow/x"),
        (["Task Board"], "/api/Task%20Board/x", True, "/api/orderflow/x"),
        (["Task Board"], "/api/x?q=Task%20Board", True, "/api/x?q=orderflow"),
        (["Acme"], "/api/acme_tasks", True, "/api/orderflow_tasks"),
    ]
    for brands, text, url_path, expected in cases:
        out, findings = _mask(text, brands, url_path=url_path)
        assert out == expected, (text, out)
        assert [f.kind for f in findings] == ["brand"], text
        assert _mask(out, brands, url_path=url_path) == (out, []), text  # idempotent
        if url_path:
            assert re.fullmatch(r"[A-Za-z0-9/_.~%?&={}-]*", out), out
    out, _ = _mask("/api/acme_tasks", ["Acme"], "Мой клон 2", url_path=True)
    assert out == "/api/product2_tasks" or re.fullmatch(r"[A-Za-z0-9/_.~%?&=-]*", out)


def test_brand_letters_inside_other_words_are_not_masked():
    for text in ("acmes", "pacman", "macme", "Acmeville", "taskboarding", "notaskboard"):
        brands = ["Acme", "Task Board"]
        assert _mask(text, brands) == (text, []), text


def test_glued_brand_in_prose_is_masked_too():
    out, findings = _clean("The taskboard_id and TaskBoardPro fields")
    assert out == "The tasklet_id and Tasklet fields"
    assert [f.kind for f in findings] == ["brand", "brand"]
    assert _clean(out) == (out, [])


def _branded_scenario() -> Scenario:
    shape = {
        "type": "object",
        "properties": {
            "TaskBoard": {"type": "string"},
            "Tasklet": {"type": "integer"},
            "meta": {"type": "object", "properties": {"taskboard_id": {"type": "integer"}},
                     "required": ["taskboard_id"]},
        },
        "required": ["TaskBoard", "Tasklet", "meta"],
    }
    return Scenario(id="S-001", title="Create", steps=[
        ScenarioStep(
            step=Step(method="POST", path="/api/x",
                      json_body={"TaskBoard": "pen", "Tasklet": 1, "meta": {"taskboard_id": 2}},
                      save={"v0": "/meta/taskboard_id"}),
            expect=Expect(status=201, json_shape=shape,
                          json_equals={"/TaskBoard": "pen", "/meta/taskboard_id": 2}),
        ),
        ScenarioStep(step=Step(method="GET", path="/api/x/{v0}"), expect=Expect(status=200)),
    ])


def test_renamed_body_keys_are_renamed_in_schema_pointers_and_save():
    from reverseai.barrier.sanitizer import sanitize_scenarios

    [out], findings = sanitize_scenarios(
        [_branded_scenario()], _index(), brand_terms=BRANDS, product_name="Tasklet",
        target_domains=DOMAINS,
    )
    step, expect = out.steps[0].step, out.steps[0].expect
    assert step.json_body == {"Tasklet_2": "pen", "Tasklet": 1, "meta": {"tasklet_id": 2}}
    assert step.save == {"v0": "/meta/tasklet_id"}
    assert expect.json_equals == {"/Tasklet_2": "pen", "/meta/tasklet_id": 2}
    assert set(expect.json_shape["properties"]) == {"Tasklet_2", "Tasklet", "meta"}
    assert expect.json_shape["required"] == ["Tasklet_2", "Tasklet", "meta"]
    assert expect.json_shape["properties"]["meta"]["required"] == ["tasklet_id"]
    assert "taskboard" not in out.model_dump_json().lower()
    locations = {f.location for f in findings}
    assert "scenarios[S-001].steps[0].expect.json_shape" in locations
    assert "scenarios[S-001].steps[0].expect.json_equals" in locations
    assert "scenarios[S-001].steps[0].save" in locations
    [again], findings2 = sanitize_scenarios(
        [out], _index(), brand_terms=BRANDS, product_name="Tasklet", target_domains=DOMAINS,
    )
    assert again == out and findings2 == []


def test_withheld_expectations_follow_renamed_pointers():
    from reverseai.barrier.sanitizer import sanitize_scenarios, withheld_expectations

    original = _branded_scenario()
    original.steps[0].expect.json_equals["/note"] = "a long sentence the server wrote back"
    [out], _ = sanitize_scenarios(
        [original], _index(), brand_terms=BRANDS, product_name="Tasklet", target_domains=DOMAINS,
    )
    assert "/note" not in out.steps[0].expect.json_equals
    assert withheld_expectations(original, out) == [(0, "/note")]


def test_spec_schemas_and_entity_fields_share_the_scenario_renames():
    from reverseai.barrier.sanitizer import key_renames, sanitize_scenarios

    spec = BehaviorSpec(
        product_name="Tasklet", summary="s", features=[], rules=[], gaps=[],
        entities=[Entity(name="Task", description="d", fields={"TaskBoard": "string"})],
        api=[ApiContract(
            method="POST", path="/api/x",
            request_schema={"type": "object", "properties": {"TaskBoard": {"type": "string"},
                                                              "Tasklet": {"type": "integer"}}},
            responses={201: {"type": "object", "properties": {"TaskBoard": {"type": "string"}}}},
        )],
    )
    renames = key_renames(spec, [_branded_scenario()], brand_terms=BRANDS,
                          product_name="Tasklet", target_domains=DOMAINS)
    clean, report = sanitize_spec(spec, _index(), brand_terms=BRANDS, target_domains=DOMAINS,
                                  renames=renames)
    [out], _ = sanitize_scenarios(
        [_branded_scenario()], _index(), brand_terms=BRANDS, product_name="Tasklet",
        target_domains=DOMAINS, renames=renames,
    )
    body_name = next(k for k in out.steps[0].step.json_body if k.startswith("Tasklet_"))
    assert body_name in clean.api[0].request_schema["properties"]
    assert body_name in clean.api[0].responses[201]["properties"]
    assert body_name in clean.entities[0].fields
    assert "taskboard" not in clean.model_dump_json().lower()
    assert "api[0].request_schema" in {f.location for f in report.findings}
