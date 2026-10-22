import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
import pytest

from reverseai.bench.server import load_target, serve_asgi

taskboard = load_target("taskboard")
HIDDEN = str(Path(taskboard.__file__).parent / "hidden_tests")


def _run_hidden(url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", HIDDEN, "-q", "-p", "no:cacheprovider"],
        env={**os.environ, "BASE_URL": url},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_hidden_tests_pass_against_original() -> None:
    with serve_asgi(taskboard.create_app()) as url:
        result = _run_hidden(url)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hidden_tests_fail_against_a_broken_server() -> None:
    from fastapi import FastAPI

    with serve_asgi(FastAPI()) as url:
        result = _run_hidden(url)
    assert result.returncode != 0


def test_hidden_tests_are_order_independent_on_a_dirty_store() -> None:
    app = taskboard.create_app()
    with serve_asgi(app) as url:
        with httpx.Client(base_url=url, trust_env=False) as c:
            for i in range(3):
                assert c.post("/api/tasks", json={"title": f"pre-{i}"}).status_code == 201
        result = _run_hidden(url)
    assert result.returncode == 0, result.stdout + result.stderr


def test_hidden_tests_pass_twice_against_the_same_server() -> None:
    with serve_asgi(taskboard.create_app()) as url:
        for _ in range(2):
            result = _run_hidden(url)
            assert result.returncode == 0, result.stdout + result.stderr


def test_serve_asgi_yields_url_and_serves_html() -> None:
    with serve_asgi(taskboard.create_app()) as url:
        r = httpx.get(url + "/", trust_env=False)
        assert r.status_code == 200
        assert "TaskBoard Pro" in r.text
        assert 'name="title"' in r.text and 'name="priority"' in r.text
        js = httpx.get(url + "/static/app.js", trust_env=False)
        assert js.status_code == 200
        assert "/api/tasks" in js.text


def test_serve_asgi_frees_port_and_stops_thread_even_on_error() -> None:
    port = None
    with pytest.raises(RuntimeError, match="boom"), serve_asgi(taskboard.create_app()) as url:
        port = int(url.rsplit(":", 1)[1])
        raise RuntimeError("boom")
    assert port is not None
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))  # would raise if still bound


def test_serve_asgi_with_explicit_port() -> None:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with serve_asgi(taskboard.create_app(), port=port) as url:
        assert url == f"http://127.0.0.1:{port}"
        assert httpx.get(url + "/api/stats", trust_env=False).status_code == 200


def test_apps_have_isolated_state_and_reset_state_restarts_ids() -> None:
    a, b = taskboard.create_app(), taskboard.create_app()
    with serve_asgi(a) as ua, serve_asgi(b) as ub:
        first = httpx.post(ua + "/api/tasks", json={"title": "x"}, trust_env=False).json()
        assert first["id"] == 1
        assert httpx.get(ub + "/api/tasks", trust_env=False).json() == []
        taskboard.reset_state(a)
        assert httpx.get(ua + "/api/tasks", trust_env=False).json() == []
        again = httpx.post(ua + "/api/tasks", json={"title": "x"}, trust_env=False).json()
        assert again["id"] == 1


def test_load_target_unknown_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_target(f"nope-{uuid.uuid4().hex}")
