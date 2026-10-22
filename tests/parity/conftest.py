import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from reverseai.bench.server import load_target, serve_asgi
from reverseai.observe.contracts import infer_endpoints
from reverseai.observe.har import Exchange
from reverseai.oracle.build import build_scenarios
from reverseai.oracle.model import Scenario

taskboard = load_target("taskboard")
TASKBOARD_SRC = Path(taskboard.__file__)

SCRIPT: list[tuple[str, str, Any]] = [
    ("POST", "/api/tasks", {"title": "write report", "priority": "high"}),
    ("POST", "/api/tasks", {"title": "write report"}),  # 409 duplicate
    ("GET", "/api/tasks/1", None),
    ("PATCH", "/api/tasks/1", {"done": True}),
    ("GET", "/api/tasks", None),
    ("GET", "/api/stats", None),
    ("DELETE", "/api/tasks/1", None),
    ("GET", "/api/tasks/1", None),
    ("POST", "/api/tasks", {"title": ""}),
    ("GET", "/api/tasks/999", None),
]


def _record(client: httpx.Client, base_url: str) -> list[Exchange]:
    exchanges = []
    for i, (method, path, body) in enumerate(SCRIPT):
        r = client.request(method, path, json=body)
        exchanges.append(
            Exchange(
                id=f"x{i}",
                method=method,
                url=base_url + path,
                path=path,
                query={},
                status=r.status_code,
                request_json=body,
                response_json=r.json() if r.content else None,
                response_content_type=r.headers.get("content-type", ""),
            )
        )
    return exchanges


def _load_clone_without_duplicate_rule(tmp_path: Path) -> Any:
    """A copy of the taskboard app that accepts duplicate titles (a missing rule)."""
    source = TASKBOARD_SRC.read_text(encoding="utf-8")
    needle = "if any(not t[\"done\"] and t[\"title\"].casefold() == wanted"
    assert needle in source
    source = source.replace(needle, "if False and any(not t[\"done\"] and t[\"title\"].casefold() == wanted")
    static = 'STATIC_DIR = Path(__file__).parent / "static"'
    assert static in source
    source = source.replace(static, f"STATIC_DIR = Path({str(TASKBOARD_SRC.parent / 'static')!r})")
    path = tmp_path / "lenient_taskboard.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("lenient_taskboard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class Server:
    url: str
    reset: Callable[[], None]


def _serve(module: Any):
    app = module.create_app()
    with serve_asgi(app) as url:
        yield Server(url=url, reset=lambda: module.reset_state(app))


@pytest.fixture
def original():
    yield from _serve(taskboard)


@pytest.fixture
def faithful_clone():
    yield from _serve(taskboard)


@pytest.fixture
def lenient_clone(tmp_path):
    yield from _serve(_load_clone_without_duplicate_rule(tmp_path))


@pytest.fixture
def scenarios(original: Server) -> list[Scenario]:
    original.reset()
    with httpx.Client(base_url=original.url, trust_env=False) as client:
        exchanges = _record(client, original.url)
    original.reset()
    return build_scenarios(exchanges, infer_endpoints(exchanges))
