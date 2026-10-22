"""TaskBoard Pro: the "original" application of the benchmark (in-memory state)."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

PRIORITIES = ("low", "normal", "high")
MAX_TITLE_LENGTH = 200
STATIC_DIR = Path(__file__).parent / "static"

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>TaskBoard Pro</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto; padding: 0 1rem; }
    form { display: flex; gap: .5rem; margin-bottom: .5rem; }
    form input[name="title"] { flex: 1; padding: .4rem; }
    #form-error { color: #b00020; min-height: 1.2rem; }
    #stats { color: #555; margin-bottom: 1rem; }
    li { display: flex; gap: .5rem; align-items: center; padding: .25rem 0; }
    li.done .title { text-decoration: line-through; color: #888; }
    .priority-high { color: #b00020; }
    .priority-low { color: #888; }
  </style>
</head>
<body>
  <h1>TaskBoard Pro</h1>
  <form id="task-form" action="/" method="post">
    <input type="text" name="title" placeholder="What needs doing?" maxlength="300" required>
    <select name="priority">
      <option value="low">low</option>
      <option value="normal" selected>normal</option>
      <option value="high">high</option>
    </select>
    <button type="submit">Add task</button>
  </form>
  <div id="form-error" role="alert"></div>
  <div id="stats"></div>
  <ul id="task-list"></ul>
  <script src="/static/app.js"></script>
</body>
</html>
"""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _error(status: int, code: str) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status)


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.tasks: dict[int, dict[str, Any]] = {}
        self.next_id = 1


def create_app() -> FastAPI:
    """Build a fresh TaskBoard app with its own empty in-memory state."""
    app = FastAPI(title="TaskBoard Pro", docs_url=None, redoc_url=None, openapi_url=None)
    state = _State()
    app.state.taskboard = state

    def find(raw_id: str) -> dict[str, Any] | None:
        try:
            return state.tasks.get(int(raw_id))
        except ValueError:
            return None

    async def read_object(request: Request) -> dict[str, Any] | None:
        try:
            body = await request.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    @app.get("/api/tasks")
    def list_tasks() -> list[dict[str, Any]]:
        with state.lock:
            return [state.tasks[i] for i in sorted(state.tasks)]

    @app.get("/api/stats")
    def stats() -> dict[str, int]:
        with state.lock:
            total = len(state.tasks)
            done = sum(1 for t in state.tasks.values() if t["done"])
        return {"total": total, "done": done, "open": total - done}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> Response:
        with state.lock:
            task = find(task_id)
            return JSONResponse(task) if task else _error(404, "not_found")

    @app.post("/api/tasks")
    async def create_task(request: Request) -> Response:
        body = await read_object(request)
        if body is None:
            return _error(422, "invalid_body")
        raw_title = body.get("title")
        title = raw_title.strip() if isinstance(raw_title, str) else ""
        if not title:
            return _error(422, "title_required")
        if len(title) > MAX_TITLE_LENGTH:
            return _error(422, "title_too_long")
        priority = body.get("priority", "normal")
        if not isinstance(priority, str) or priority not in PRIORITIES:
            return _error(422, "invalid_priority")
        with state.lock:
            wanted = title.casefold()
            if any(not t["done"] and t["title"].casefold() == wanted for t in state.tasks.values()):
                return _error(409, "duplicate")
            task = {
                "id": state.next_id,
                "title": title,
                "priority": priority,
                "done": False,
                "created_at": _now_iso(),
            }
            state.tasks[task["id"]] = task
            state.next_id += 1
        return JSONResponse(task, status_code=201)

    @app.patch("/api/tasks/{task_id}")
    async def update_task(task_id: str, request: Request) -> Response:
        with state.lock:
            if find(task_id) is None:
                return _error(404, "not_found")
        body = await read_object(request)
        if body is None:
            return _error(422, "invalid_body")
        done = body.get("done")
        if not isinstance(done, bool):
            return _error(422, "invalid_done")
        with state.lock:
            task = find(task_id)
            if task is None:
                return _error(404, "not_found")
            task["done"] = done
            return JSONResponse(task)

    @app.delete("/api/tasks/{task_id}")
    def delete_task(task_id: str) -> Response:
        with state.lock:
            task = find(task_id)
            if task is None:
                return _error(404, "not_found")
            del state.tasks[task["id"]]
        return Response(status_code=204)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def reset_state(app: FastAPI) -> None:
    """Clear `app`'s tasks and restart ids at 1 (Python-level helper, not an endpoint)."""
    state: _State = app.state.taskboard
    with state.lock:
        state.tasks.clear()
        state.next_id = 1
