import pytest

from reverseai.oracle import normalize, standalone
from reverseai.oracle.standalone import check_shape, json_equal, resolve_pointer


def test_normalize_timestamps_and_uuids() -> None:
    doc = {
        "id": 3,
        "created_at": "2026-10-20T12:30:00Z",
        "updated": "2026-10-20T12:30:00.123456+02:00",
        "token": "123e4567-e89b-12d3-a456-426614174000",
        "items": [{"at": "2026-01-01T00:00:00"}, "plain", 7, None, True],
        "due": "2026-10-20",
        "title": "buy milk",
    }
    assert normalize.normalize(doc) == {
        "id": 3,
        "created_at": "<volatile>",
        "updated": "<volatile>",
        "token": "<volatile>",
        "items": [{"at": "<volatile>"}, "plain", 7, None, True],
        "due": "2026-10-20",
        "title": "buy milk",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-20T12:30:00Z", True),
        ("2026-10-20 12:30:00", True),
        ("123E4567-E89B-12D3-A456-426614174000", True),
        ("2026-10-20", False),
        ("2026-13-45T99:99:00", False),
        ("not a date", False),
        (5, False),
        (None, False),
    ],
)
def test_is_volatile(value, expected) -> None:
    assert normalize.is_volatile(value) is expected


def test_normalize_module_reuses_standalone_implementation() -> None:
    assert normalize.normalize is standalone.normalize
    assert normalize.is_volatile is standalone.is_volatile


TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "title": {"type": "string"},
        "done": {"type": "boolean"},
        "created_at": {"type": "string", "format": "date-time"},
        "note": {"type": ["null", "string"]},
    },
    "required": ["created_at", "done", "id", "title"],
}


def test_check_shape_reports_missing_required() -> None:
    value = {"id": 1, "done": False, "created_at": "2026-10-20T12:30:00Z"}
    assert check_shape(TASK_SCHEMA, value) == ["/title"]


def test_check_shape_accepts_valid_value_with_extra_keys() -> None:
    value = {
        "id": 1,
        "title": "a",
        "done": False,
        "created_at": "2026-10-20T12:30:00Z",
        "note": None,
        "extra": [1, 2],
    }
    assert check_shape(TASK_SCHEMA, value) == []


def test_check_shape_type_rules() -> None:
    bad = {"id": True, "title": 5, "done": "no", "created_at": "yesterday", "note": 3}
    assert sorted(check_shape(TASK_SCHEMA, bad)) == [
        "/created_at",
        "/done",
        "/id",
        "/note",
        "/title",
    ]
    assert check_shape({"type": "number"}, 3) == []
    assert check_shape({"type": "number"}, 3.5) == []
    assert check_shape({"type": "integer"}, 3.5) == [""]
    assert check_shape({"type": "null"}, None) == []
    assert check_shape({"type": "object"}, None) == [""]
    assert check_shape({}, "anything") == []


def test_check_shape_recurses_into_items_and_escapes_pointers() -> None:
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"a/b": {"type": "integer"}, "c~d": {"type": "string"}},
            "required": ["a/b", "c~d"],
        },
    }
    value = [{"a/b": 1, "c~d": "x"}, {"a/b": "one"}]
    assert check_shape(schema, value) == ["/1/c~0d", "/1/a~1b"]  # required first


def test_resolve_pointer_rfc6901() -> None:
    doc = {"a": [{"b": 1}], "x/y": 2, "m~n": 3, "": 4}
    assert resolve_pointer(doc, "") == (True, doc)
    assert resolve_pointer(doc, "/a/0/b") == (True, 1)
    assert resolve_pointer(doc, "/x~1y") == (True, 2)
    assert resolve_pointer(doc, "/m~0n") == (True, 3)
    assert resolve_pointer(doc, "/") == (True, 4)
    assert resolve_pointer(doc, "/a/1/b") == (False, None)
    assert resolve_pointer(doc, "/a/-1") == (False, None)
    assert resolve_pointer(doc, "/missing") == (False, None)
    assert resolve_pointer(5, "/a") == (False, None)


def test_json_equal_is_type_strict_for_booleans() -> None:
    assert json_equal(1, 1)
    assert json_equal(1, 1.0)
    assert not json_equal(True, 1)
    assert not json_equal(0, False)
    assert json_equal({"a": [1, "x"]}, {"a": [1, "x"]})
    assert not json_equal({"a": [True]}, {"a": [1]})
    assert not json_equal([1], [1, 2])
    assert not json_equal({"a": 1}, {"a": 1, "b": 2})
