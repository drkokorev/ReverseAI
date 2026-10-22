"""Tasklet: a shared in-memory task board.

Clean-room implementation written only from the released behavior spec
(tests/fixtures/llm/analyst_spec.json). Used as the scripted executor's final answer.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

PRIORITIES = ("low", "normal", "high")
DEFAULT_PRIORITY = "normal"
TITLE_LIMIT = 200

app = FastAPI()


class Board:
    """Process-local state: one board for everybody, emptied by a restart (R-012)."""

    def __init__(self) -> None:
        self.items: dict[int, dict[str, Any]] = {}
        self.last_id = 0

    def issue_id(self) -> int:
        self.last_id += 1  # ids are never handed out twice, even after deletes (R-008)
        return self.last_id

    def find(self, raw_id: str) -> dict[str, Any] | None:
        try:
            key = int(raw_id)
        except ValueError:
            return None
        return self.items.get(key)

    def ordered(self) -> list[dict[str, Any]]:
        return [self.items[key] for key in sorted(self.items)]

    def has_open_title(self, title: str) -> bool:
        wanted = title.casefold()
        return any(
            not item["done"] and item["title"].casefold() == wanted
            for item in self.items.values()
        )


board = Board()


def fail(status: int, code: str) -> JSONResponse:
    """Error answers carry exactly one key, a machine code (R-001)."""
    return JSONResponse({"error": code}, status_code=status)


@app.exception_handler(StarletteHTTPException)
async def coded_http_errors(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code == 404:
        return fail(404, "not_found")
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


async def object_body(request: Request) -> dict[str, Any] | None:
    """The parsed body when it is a JSON object, else None (R-002)."""
    raw = await request.body()
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@app.post("/api/tasks")
async def create_task(request: Request) -> Response:
    payload = await object_body(request)
    if payload is None:
        return fail(422, "invalid_body")

    title = payload.get("title")
    title = title.strip() if isinstance(title, str) else ""
    if not title:
        return fail(422, "title_required")
    if len(title) > TITLE_LIMIT:
        return fail(422, "title_too_long")

    priority = payload.get("priority", DEFAULT_PRIORITY)
    if not isinstance(priority, str) or priority not in PRIORITIES:
        return fail(422, "invalid_priority")

    if board.has_open_title(title):
        return fail(409, "duplicate")

    task = {
        "id": board.issue_id(),
        "title": title,
        "priority": priority,
        "done": False,
        "created_at": utc_stamp(),
    }
    board.items[task["id"]] = task
    return JSONResponse(task, status_code=201)


@app.get("/api/tasks")
async def list_tasks() -> Response:
    return JSONResponse(board.ordered())


@app.get("/api/tasks/{task_id}")
async def read_task(task_id: str) -> Response:
    task = board.find(task_id)
    if task is None:
        return fail(404, "not_found")
    return JSONResponse(task)


@app.patch("/api/tasks/{task_id}")
async def set_done(task_id: str, request: Request) -> Response:
    task = board.find(task_id)
    if task is None:
        return fail(404, "not_found")
    payload = await object_body(request)
    if payload is None:
        return fail(422, "invalid_body")
    flag = payload.get("done")
    if not isinstance(flag, bool):
        return fail(422, "invalid_done")
    task["done"] = flag
    return JSONResponse(task)


@app.delete("/api/tasks/{task_id}")
async def remove_task(task_id: str) -> Response:
    task = board.find(task_id)
    if task is None:
        return fail(404, "not_found")
    del board.items[task["id"]]
    return Response(status_code=204)


@app.get("/api/stats")
async def counters() -> Response:
    total = len(board.items)
    finished = sum(1 for item in board.items.values() if item["done"])
    return JSONResponse({"total": total, "done": finished, "open": total - finished})


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tasklet</title>
<style>
  body { font: 15px/1.4 system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; }
  li.finished span.name { text-decoration: line-through; opacity: .6; }
  .tag { font-size: .8em; padding: 0 .4em; border: 1px solid #999; border-radius: 3px; }
  #problem { color: #b00; min-height: 1.2em; }
</style>
</head>
<body>
<h1>Tasklet</h1>
<form id="composer">
  <input id="what" placeholder="New task" autocomplete="off">
  <select id="level">
    <option value="low">low</option>
    <option value="normal" selected>normal</option>
    <option value="high">high</option>
  </select>
  <button>Save</button>
</form>
<p id="problem"></p>
<p id="tally"></p>
<ul id="rows"></ul>
<script>
const NOTICES = {
  title_required: "Please type a task name.",
  title_too_long: "Task names are limited to 200 characters.",
  invalid_priority: "Choose low, normal or high.",
  duplicate: "An unfinished task already has this name.",
};

async function call(verb, url, data) {
  const init = { method: verb };
  if (data !== undefined) {
    init.headers = { "content-type": "application/json" };
    init.body = JSON.stringify(data);
  }
  const reply = await fetch(url, init);
  const parsed = reply.status === 204 ? null : await reply.json();
  return { ok: reply.ok, parsed };
}

function row(task) {
  const li = document.createElement("li");
  li.className = task.done ? "finished" : "";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = task.done;
  box.onchange = () => call("PATCH", "/api/tasks/" + task.id, { done: box.checked }).then(redraw);
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = " " + task.title + " ";
  const tag = document.createElement("span");
  tag.className = "tag";
  tag.textContent = task.priority;
  const drop = document.createElement("button");
  drop.textContent = "x";
  drop.onclick = () => call("DELETE", "/api/tasks/" + task.id).then(redraw);
  li.append(box, name, tag, " ", drop);
  return li;
}

async function redraw() {
  const [list, stats] = await Promise.all([call("GET", "/api/tasks"), call("GET", "/api/stats")]);
  document.getElementById("rows").replaceChildren(...list.parsed.map(row));
  const s = stats.parsed;
  document.getElementById("tally").textContent =
    s.total + " in all, " + s.open + " to do, " + s.done + " finished";
}

document.getElementById("composer").onsubmit = async (event) => {
  event.preventDefault();
  const what = document.getElementById("what");
  const level = document.getElementById("level").value;
  const outcome = await call("POST", "/api/tasks", { title: what.value, priority: level });
  document.getElementById("problem").textContent =
    outcome.ok ? "" : NOTICES[outcome.parsed.error] || outcome.parsed.error;
  if (outcome.ok) what.value = "";
  redraw();
};

redraw();
</script>
</body>
</html>
"""


@app.get("/")
async def page() -> HTMLResponse:
    return HTMLResponse(PAGE)
