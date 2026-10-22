from typing import Any

from reverseai.observe.contracts import infer_endpoints
from reverseai.observe.har import Exchange
from reverseai.oracle.build import build_scenarios
from reverseai.oracle.model import Scenario

TS = "2026-10-20T12:30:00Z"


def ex(
    id: str,
    method: str,
    path: str,
    status: int,
    request_json: Any = None,
    response_json: Any = None,
    query: dict[str, str] | None = None,
    error: str | None = None,
) -> Exchange:
    return Exchange(
        id=id,
        method=method,
        url=f"http://h{path}",
        path=path,
        query=query or {},
        status=status,
        request_json=request_json,
        response_json=response_json,
        response_content_type="application/json",
        error=error,
    )


def build(exchanges: list[Exchange]) -> list[Scenario]:
    return build_scenarios(exchanges, infer_endpoints(exchanges))


def task(id: int, title: str = "a", done: bool = False) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "priority": "normal",
        "done": done,
        "created_at": TS,
    }


def test_build_links_create_then_get() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 201, {"title": "a"}, task(5)),
        ex("e2", "GET", "/api/tasks/5", 200, None, task(5)),
    ]
    [scenario] = build(exchanges)
    assert scenario.id == "s001"
    assert scenario.title == "POST /api/tasks → 201, then GET /api/tasks/{id} → 200"
    assert scenario.source_exchanges == ["e1", "e2"]
    assert scenario.critical is True
    first, second = scenario.steps
    assert first.step.method == "POST"
    assert first.step.path == "/api/tasks"
    assert first.step.json_body == {"title": "a"}
    assert first.step.save == {"v0": "/id"}
    assert first.expect.status == 201
    assert first.expect.json_shape is not None
    assert first.expect.json_shape["required"] == [
        "created_at",
        "done",
        "id",
        "priority",
        "title",
    ]
    assert second.step.path == "/api/tasks/{v0}"
    assert second.step.save == {}
    assert second.expect.status == 200


def test_build_marks_error_code_constant() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 422, {"title": ""}, {"error": "title_required"}),
        ex(
            "e2",
            "POST",
            "/api/tasks",
            422,
            {"title": "  "},
            {"error": "title_required"},
        ),
    ]
    scenarios = build(exchanges)
    # identical (method, template, status, body keys) signature -> deduplicated
    assert [s.source_exchanges for s in scenarios] == [["e1"]]
    expect = scenarios[0].steps[0].expect
    assert expect.json_equals["/error"] == "title_required"
    assert scenarios[0].critical is False


def test_single_error_example_keeps_error_code() -> None:
    exchanges = [ex("e1", "GET", "/api/tasks/9", 404, None, {"error": "not_found"})]
    [scenario] = build(exchanges)
    assert scenario.steps[0].expect.json_equals == {"/error": "not_found"}
    assert scenario.steps[0].step.path == "/api/tasks/9"
    assert scenario.title == "GET /api/tasks/{id} → 404"


def test_echo_and_constant_fields_exclude_ids_and_volatile_values() -> None:
    exchanges = [
        ex(
            "e1",
            "POST",
            "/api/tasks",
            201,
            {"title": "a", "owner_id": 7},
            task(1, "a") | {"owner_id": 7},
        ),
        ex(
            "e2",
            "POST",
            "/api/tasks",
            201,
            {"title": "b", "owner_id": 7},
            task(2, "b") | {"owner_id": 7},
        ),
    ]
    scenarios = build(exchanges)
    # echoed titles differ, so the json_equals part of the signature keeps both
    assert [s.source_exchanges for s in scenarios] == [["e1"], ["e2"]]
    # echo of the request title, constants "priority"/"done"; never ids or timestamps
    assert scenarios[0].steps[0].expect.json_equals == {
        "/title": "a",
        "/priority": "normal",
        "/done": False,
    }
    assert scenarios[1].steps[0].expect.json_equals["/title"] == "b"


def test_echo_compares_raw_values() -> None:
    exchanges = [ex("e1", "POST", "/api/tasks", 201, {"title": "  a "}, task(1, "a"))]
    [scenario] = build(exchanges)
    assert "/title" not in scenario.steps[0].expect.json_equals


def test_single_success_example_has_no_constants() -> None:
    exchanges = [
        ex("e1", "GET", "/api/stats", 200, None, {"total": 0, "done": 0, "open": 0})
    ]
    [scenario] = build(exchanges)
    assert scenario.steps[0].expect.json_equals == {}
    assert scenario.critical is False


def test_constant_requires_identical_values() -> None:
    exchanges = [
        ex("e1", "GET", "/api/stats", 200, None, {"total": 0, "open": 0}),
        ex("e2", "GET", "/api/stats", 200, None, {"total": 1, "open": 0}),
    ]
    scenarios = build(exchanges)
    assert len(scenarios) == 1
    assert scenarios[0].steps[0].expect.json_equals == {"/open": 0}


def test_chain_reuses_variables_and_prefers_most_recent_producer() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 201, {"title": "a"}, task(1)),
        ex(
            "e2", "GET", "/api/tasks", 200, None, [task(1)]
        ),  # top-level lists never link
        ex("e3", "PATCH", "/api/tasks/1", 200, {"done": True}, task(1, done=True)),
        ex("e4", "DELETE", "/api/tasks/1", 204),
        ex("e5", "GET", "/api/tasks/1", 404, None, {"error": "not_found"}),
    ]
    scenarios = build(exchanges)
    assert [s.id for s in scenarios] == ["s001", "s002"]
    chain, listing = scenarios
    assert chain.source_exchanges == ["e1", "e3", "e4", "e5"]
    assert [s.step.path for s in chain.steps] == [
        "/api/tasks",
        "/api/tasks/{v0}",
        "/api/tasks/{v1}",
        "/api/tasks/{v1}",
    ]
    assert chain.steps[0].step.save == {"v0": "/id"}
    assert chain.steps[1].step.save == {"v1": "/id"}
    assert chain.steps[1].expect.json_equals == {"/done": True}
    assert chain.steps[2].expect.json_shape is None
    assert chain.steps[3].expect.json_equals == {"/error": "not_found"}
    assert listing.source_exchanges == ["e2"]
    assert listing.critical is False


def test_variable_names_restart_per_scenario() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 201, {"title": "a"}, task(1)),
        ex("e2", "GET", "/api/tasks/1", 200, None, task(1)),
        ex("e3", "POST", "/api/items", 201, {"name": "x"}, {"id": "abc-1"}),
        ex("e4", "DELETE", "/api/items/abc-1", 204),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1", "e2"], ["e3", "e4"]]
    assert scenarios[1].steps[0].step.save == {"v0": "/id"}
    assert scenarios[1].steps[1].step.path == "/api/items/{v0}"


def test_literal_path_segments_are_not_linked_from_non_id_keys() -> None:
    exchanges = [
        ex("e1", "GET", "/api/kind", 200, None, {"kind": "tasks"}),
        ex("e2", "GET", "/api/tasks", 200, None, []),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1"], ["e2"]]
    assert scenarios[1].steps[0].step.path == "/api/tasks"


def test_query_is_kept_and_errored_exchanges_are_skipped() -> None:
    exchanges = [
        ex("e1", "GET", "/api/tasks", 200, None, [], query={"done": "true"}),
        ex("e2", "GET", "/api/broken", 200, None, None, error="invalid_json"),
    ]
    [scenario] = build(exchanges)
    assert scenario.steps[0].step.path == "/api/tasks?done=true"


def test_dedup_considers_body_keys() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 422, {"title": ""}, {"error": "title_required"}),
        ex(
            "e2",
            "POST",
            "/api/tasks",
            422,
            {"title": "a", "priority": "x"},
            {"error": "invalid_priority"},
        ),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1"], ["e2"]]
    # not constant across the endpoint, but each error response pins its own code
    assert scenarios[0].steps[0].expect.json_equals == {"/error": "title_required"}
    assert scenarios[1].steps[0].expect.json_equals == {"/error": "invalid_priority"}


def test_error_codes_with_same_body_keys_stay_separate() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 422, {"title": ""}, {"error": "title_required"}),
        ex(
            "e2",
            "POST",
            "/api/tasks",
            422,
            {"title": "x" * 300},
            {"error": "title_too_long"},
        ),
        ex(
            "e3", "POST", "/api/tasks", 422, {"title": " "}, {"error": "title_required"}
        ),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1"], ["e2"]]
    assert scenarios[0].steps[0].expect.json_equals == {"/error": "title_required"}
    assert scenarios[1].steps[0].expect.json_equals == {"/error": "title_too_long"}


def test_error_fields_skip_ids_and_volatile_values() -> None:
    body = {
        "error": "conflict",
        "task_id": 4,
        "at": TS,
        "detail": {"x": 1},
        "retry": False,
    }
    exchanges = [ex("e1", "PUT", "/api/tasks/4", 409, {"title": "abc"}, body)]
    [scenario] = build(exchanges)
    assert scenario.steps[0].expect.json_equals == {
        "/error": "conflict",
        "/retry": False,
    }


def test_duplicate_submission_chains_by_shared_request_value() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 201, {"title": "Alpha"}, task(1, "Alpha")),
        ex("e2", "GET", "/api/stats", 200, None, {"total": 1}),
        ex("e3", "POST", "/api/tasks", 409, {"title": "Alpha"}, {"error": "duplicate"}),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1", "e3"], ["e2"]]
    chain = scenarios[0]
    assert chain.title == "POST /api/tasks → 201, then POST /api/tasks → 409"
    assert chain.steps[1].step.json_body == {"title": "Alpha"}
    assert chain.steps[1].step.save == {}
    assert chain.steps[1].expect.status == 409
    assert chain.steps[1].expect.json_equals == {"/error": "duplicate"}


def test_shared_values_chain_only_from_earlier_writes_and_long_strings() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 201, {"title": "ab"}, task(1, "ab")),
        ex("e2", "POST", "/api/tasks", 409, {"title": "ab"}, {"error": "duplicate"}),
        ex("e3", "DELETE", "/api/things", 200, {"name": "zeta"}, {"ok": True}),
        ex("e4", "POST", "/api/things", 201, {"name": "zeta"}, {"name": "zeta"}),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1"], ["e2"], ["e3"], ["e4"]]


def test_scenarios_dump_to_plain_dicts() -> None:
    exchanges = [ex("e1", "POST", "/api/tasks", 201, {"title": "a"}, task(1))]
    [scenario] = build(exchanges)
    dumped = scenario.model_dump()
    assert dumped["steps"][0]["step"] == {
        "method": "POST",
        "path": "/api/tasks",
        "json_body": {"title": "a"},
        "save": {},
    }
    assert set(dumped["steps"][0]["expect"]) == {"status", "json_shape", "json_equals"}


def test_id_keys_win_over_more_recent_counters() -> None:
    exchanges = [
        ex("e1", "POST", "/api/tasks", 201, {"title": "a"}, task(1)),
        ex("e2", "GET", "/api/stats", 200, None, {"total": 1, "done": 1}),
        ex("e3", "DELETE", "/api/tasks/1", 204),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1", "e3"], ["e2"]]


def test_non_id_key_links_templated_segment_when_no_id_matches() -> None:
    exchanges = [
        ex("e1", "GET", "/api/latest", 200, None, {"latest": 42}),
        ex("e2", "GET", "/api/tasks/42", 200, None, task(42)),
    ]
    [scenario] = build(exchanges)
    assert scenario.steps[0].step.save == {"v0": "/latest"}
    assert scenario.steps[1].step.path == "/api/tasks/{v0}"


def test_shared_values_chain_only_on_same_key() -> None:
    exchanges = [
        ex("e1", "POST", "/api/notes", 201, {"title": "Alpha"}, {"ok": True}),
        ex("e2", "POST", "/api/notes", 201, {"tag": "Alpha"}, {"ok": True}),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1"], ["e2"]]


def test_enum_like_values_do_not_chain_but_duplicate_titles_do() -> None:
    exchanges = [
        ex(
            "e1",
            "POST",
            "/api/tasks",
            201,
            {"title": "Alpha", "priority": "high"},
            task(1, "Alpha"),
        ),
        ex(
            "e2",
            "POST",
            "/api/tasks",
            201,
            {"title": "Beta", "priority": "high"},
            task(2, "Beta"),
        ),
        ex(
            "e3",
            "POST",
            "/api/tasks",
            201,
            {"title": "Gamma", "priority": "high"},
            task(3, "Gamma"),
        ),
        ex(
            "e4",
            "POST",
            "/api/tasks",
            409,
            {"title": "Beta", "priority": "high"},
            {"error": "duplicate"},
        ),
    ]
    scenarios = build(exchanges)
    assert [s.source_exchanges for s in scenarios] == [["e1"], ["e2", "e4"], ["e3"]]
    assert scenarios[1].steps[1].expect.json_equals == {"/error": "duplicate"}
