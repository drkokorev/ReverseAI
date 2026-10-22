"""Hidden behavior tests for the TaskBoard API.

Run with BASE_URL pointing at the application under test. Tests are independent
of execution order and of store contents: titles are unique and ids come from
responses.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator

import httpx
import pytest

ISO_8601 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=os.environ["BASE_URL"], trust_env=False, timeout=10.0) as c:
        yield c


def unique_title(prefix: str = "task") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def create(client: httpx.Client, **body: object) -> httpx.Response:
    body.setdefault("title", unique_title())
    return client.post("/api/tasks", json=body)


def test_create_returns_201_with_full_shape(client: httpx.Client) -> None:
    title = unique_title()
    r = create(client, title=title, priority="high")
    assert r.status_code == 201
    task = r.json()
    assert set(task) == {"id", "title", "priority", "done", "created_at"}
    assert isinstance(task["id"], int) and not isinstance(task["id"], bool)
    assert task["title"] == title
    assert task["priority"] == "high"
    assert task["done"] is False
    assert ISO_8601.match(task["created_at"])


def test_priority_defaults_to_normal(client: httpx.Client) -> None:
    assert create(client).json()["priority"] == "normal"


def test_title_is_trimmed(client: httpx.Client) -> None:
    title = unique_title()
    assert create(client, title=f"   {title}  ").json()["title"] == title


@pytest.mark.parametrize("title", ["", "   ", None])
def test_empty_or_blank_title_is_rejected(client: httpx.Client, title: str | None) -> None:
    r = client.post("/api/tasks", json={"title": title})
    assert r.status_code == 422
    assert r.json() == {"error": "title_required"}


def test_missing_title_is_rejected(client: httpx.Client) -> None:
    r = client.post("/api/tasks", json={"priority": "low"})
    assert r.status_code == 422
    assert r.json() == {"error": "title_required"}


def test_title_length_boundary(client: httpx.Client) -> None:
    ok = create(client, title=uuid.uuid4().hex + "a" * (200 - 32))
    assert ok.status_code == 201
    too_long = create(client, title="b" * 201)
    assert too_long.status_code == 422
    assert too_long.json() == {"error": "title_too_long"}


def test_invalid_priority_is_rejected(client: httpx.Client) -> None:
    r = create(client, priority="urgent")
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_priority"}


def test_title_error_takes_precedence_over_priority_error(client: httpx.Client) -> None:
    r = client.post("/api/tasks", json={"title": "", "priority": "urgent"})
    assert r.json() == {"error": "title_required"}


def test_priority_error_takes_precedence_over_duplicate(client: httpx.Client) -> None:
    title = unique_title()
    assert create(client, title=title).status_code == 201
    r = create(client, title=title, priority="urgent")
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_priority"}


def test_non_object_body_is_rejected(client: httpx.Client) -> None:
    r = client.post("/api/tasks", json=["not", "an", "object"])
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_body"}


def test_duplicate_open_title_is_rejected_case_insensitively(client: httpx.Client) -> None:
    title = unique_title("Dup")
    assert create(client, title=title).status_code == 201
    r = create(client, title=title.upper())
    assert r.status_code == 409
    assert r.json() == {"error": "duplicate"}


def test_title_of_a_done_task_can_be_reused(client: httpx.Client) -> None:
    title = unique_title()
    first = create(client, title=title).json()
    client.patch(f"/api/tasks/{first['id']}", json={"done": True})
    second = create(client, title=title)
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]


def test_ids_are_unique_and_increasing(client: httpx.Client) -> None:
    a = create(client).json()["id"]
    b = create(client).json()["id"]
    assert b > a


def test_get_returns_created_task(client: httpx.Client) -> None:
    task = create(client).json()
    r = client.get(f"/api/tasks/{task['id']}")
    assert r.status_code == 200
    assert r.json() == task


def test_get_unknown_task_is_404(client: httpx.Client) -> None:
    r = client.get("/api/tasks/987654321")
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_list_is_ordered_by_id_and_contains_created_tasks(client: httpx.Client) -> None:
    created = [create(client).json() for _ in range(3)]
    r = client.get("/api/tasks")
    assert r.status_code == 200
    listed = r.json()
    ids = [t["id"] for t in listed]
    assert ids == sorted(ids)
    by_id = {t["id"]: t for t in listed}
    for task in created:
        assert by_id[task["id"]] == task


def test_patch_sets_and_clears_done(client: httpx.Client) -> None:
    task = create(client).json()
    r = client.patch(f"/api/tasks/{task['id']}", json={"done": True})
    assert r.status_code == 200
    assert r.json() == {**task, "done": True}
    assert client.get(f"/api/tasks/{task['id']}").json()["done"] is True
    r = client.patch(f"/api/tasks/{task['id']}", json={"done": False})
    assert r.json()["done"] is False


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_patch_rejects_non_bool_done(client: httpx.Client, value: object) -> None:
    task = create(client).json()
    r = client.patch(f"/api/tasks/{task['id']}", json={"done": value})
    assert r.status_code == 422
    assert r.json() == {"error": "invalid_done"}


def test_patch_unknown_task_is_404(client: httpx.Client) -> None:
    r = client.patch("/api/tasks/987654321", json={"done": True})
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_delete_removes_task(client: httpx.Client) -> None:
    task = create(client).json()
    r = client.delete(f"/api/tasks/{task['id']}")
    assert r.status_code == 204
    assert r.content == b""
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404
    assert task["id"] not in [t["id"] for t in client.get("/api/tasks").json()]


def test_delete_unknown_task_is_404(client: httpx.Client) -> None:
    r = client.delete("/api/tasks/987654321")
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_stats_reflect_changes(client: httpx.Client) -> None:
    before = client.get("/api/stats").json()
    assert set(before) == {"total", "done", "open"}
    assert before["total"] == before["done"] + before["open"]

    a = create(client).json()
    b = create(client).json()
    after_create = client.get("/api/stats").json()
    assert after_create["total"] == before["total"] + 2
    assert after_create["open"] == before["open"] + 2

    client.patch(f"/api/tasks/{a['id']}", json={"done": True})
    after_done = client.get("/api/stats").json()
    assert after_done["done"] == before["done"] + 1
    assert after_done["open"] == before["open"] + 1

    client.delete(f"/api/tasks/{a['id']}")
    client.delete(f"/api/tasks/{b['id']}")
    final = client.get("/api/stats").json()
    assert final["total"] == before["total"]
    assert final["done"] == before["done"]
