import json
from pathlib import Path

from reverseai.observe.contracts import (
    Endpoint,
    infer_endpoints,
    infer_schema,
    template_path,
)
from reverseai.observe.har import Exchange, parse_har

FIXTURE = Path(__file__).parent.parent / "fixtures" / "taskboard.har"


def make_exchange(
    id: str,
    method: str = "GET",
    path: str = "/api/tasks/1",
    status: int = 200,
    request_json=None,
    response_json=None,
    error: str | None = None,
) -> Exchange:
    return Exchange(
        id=id,
        method=method,
        url=f"http://h{path}",
        path=path,
        query={},
        status=status,
        request_json=request_json,
        response_json=response_json,
        response_content_type="application/json",
        error=error,
    )


def test_template_path() -> None:
    assert template_path("/api/tasks/17") == "/api/tasks/{id}"
    assert template_path("/api/tasks") == "/api/tasks"
    assert template_path("/") == "/"
    assert template_path("/api/tasks/17/") == "/api/tasks/{id}/"
    assert template_path("/u/123e4567-e89b-12d3-a456-426614174000/x") == "/u/{id}/x"
    assert template_path("/api/v2/tasks") == "/api/v2/tasks"
    assert template_path("/api/t1/12ab") == "/api/t1/12ab"


def test_infer_schema_empty_and_scalars() -> None:
    assert infer_schema([]) == {}
    assert infer_schema(["a", "b"]) == {"type": "string"}
    assert infer_schema([1, 2]) == {"type": "integer"}
    assert infer_schema([1, 2.5]) == {"type": "number"}
    assert infer_schema([True, False]) == {"type": "boolean"}
    assert infer_schema([1, True]) == {"type": ["boolean", "integer"]}
    assert infer_schema([None]) == {"type": "null"}
    assert infer_schema(["a", None]) == {"type": ["null", "string"]}


def test_infer_schema_required_and_datetime() -> None:
    schema = infer_schema(
        [
            {"id": 1, "created_at": "2026-10-20T09:00:00Z", "note": "x"},
            {"id": 2, "created_at": "2026-10-20T09:05:00+00:00"},
        ]
    )
    assert schema["type"] == "object"
    assert schema["required"] == ["created_at", "id"]
    assert schema["properties"]["id"] == {"type": "integer"}
    assert schema["properties"]["created_at"] == {"type": "string", "format": "date-time"}
    assert schema["properties"]["note"] == {"type": "string"}


def test_infer_schema_datetime_needs_all_strings_to_match() -> None:
    assert infer_schema(["2026-10-20T09:00:00Z", "tomorrow"]) == {"type": "string"}
    assert infer_schema(["2026-10-20"]) == {"type": "string"}
    assert infer_schema(["2026-10-20T09:00:00Z", None]) == {
        "type": ["null", "string"],
        "format": "date-time",
    }


def test_infer_schema_arrays_merge_items() -> None:
    schema = infer_schema([[{"id": 1}, {"id": 2, "x": "a"}], []])
    assert schema["type"] == "array"
    assert schema["items"]["type"] == "object"
    assert schema["items"]["required"] == ["id"]
    assert set(schema["items"]["properties"]) == {"id", "x"}
    assert infer_schema([[]]) == {"type": "array", "items": {}}


def test_infer_schema_mixed_object_and_scalar() -> None:
    schema = infer_schema([{"a": 1}, "s"])
    assert schema["type"] == ["object", "string"]
    assert schema["required"] == ["a"]
    assert schema["properties"] == {"a": {"type": "integer"}}


def test_infer_endpoints_groups() -> None:
    exchanges = [
        make_exchange("a", path="/api/tasks/1", response_json={"id": 1}),
        make_exchange("b", path="/api/tasks/2", status=404, response_json={"error": "not_found"}),
        make_exchange("c", path="/api/tasks/3", response_json={"id": 3}),
        make_exchange("d", method="POST", path="/api/tasks", status=201, request_json={"title": "t"}, response_json={"id": 4}),
        make_exchange("e", path="/api/tasks/9", error="invalid_json"),
    ]
    endpoints = infer_endpoints(exchanges)
    assert [(e.method, e.path_template) for e in endpoints] == [
        ("GET", "/api/tasks/{id}"),
        ("POST", "/api/tasks"),
    ]
    get = endpoints[0]
    assert isinstance(get, Endpoint)
    assert get.statuses == [200, 404]
    assert get.exchange_ids == ["a", "b", "c"]
    assert get.request_schema is None
    assert get.response_schemas[200]["required"] == ["id"]
    assert get.response_schemas[404]["properties"] == {"error": {"type": "string"}}
    post = endpoints[1]
    assert post.request_schema is not None and post.request_schema["required"] == ["title"]
    assert post.statuses == [201]


def test_infer_endpoints_no_content_status_gets_empty_schema() -> None:
    endpoints = infer_endpoints([make_exchange("a", method="DELETE", status=204)])
    assert endpoints[0].response_schemas == {204: {}}


def test_infer_endpoints_on_fixture() -> None:
    result = parse_har(json.loads(FIXTURE.read_text()), ["127.0.0.1"])
    endpoints = infer_endpoints(result.exchanges)
    keys = [(e.method, e.path_template, e.statuses) for e in endpoints]
    assert keys == [
        ("DELETE", "/api/tasks/{id}", [204]),
        ("GET", "/api/stats", [200]),
        ("GET", "/api/tasks", [200]),
        ("GET", "/api/tasks/{id}", [200, 404]),
        ("PATCH", "/api/tasks/{id}", [200]),
        ("POST", "/api/tasks", [201, 422]),
    ]
    post = endpoints[-1]
    assert post.request_schema["required"] == ["title"]
    assert post.request_schema["properties"]["priority"] == {"type": "string"}
    assert post.response_schemas[201]["properties"]["created_at"]["format"] == "date-time"
