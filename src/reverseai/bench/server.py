"""Helpers to load benchmark targets and serve ASGI apps on a real port."""

from __future__ import annotations

import contextlib
import importlib.util
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import uvicorn

ASGIApp = Any

_STARTUP_TIMEOUT_S = 15.0
_SHUTDOWN_TIMEOUT_S = 10.0


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "bench" / "targets").is_dir():
            return parent
    raise FileNotFoundError("could not locate a directory containing bench/targets")


def load_target(name: str) -> ModuleType:
    """Import `<repo>/bench/targets/<name>/app.py` by file path."""
    path = _repo_root() / "bench" / "targets" / name / "app.py"
    if not path.is_file():
        raise FileNotFoundError(f"benchmark target {name!r} not found at {path}")
    spec = importlib.util.spec_from_file_location(f"reverseai_bench_target_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load benchmark target {name!r} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextlib.contextmanager
def serve_asgi(app: ASGIApp, port: int | None = None) -> Iterator[str]:
    """Run `app` under uvicorn in a thread; yield its base URL once it answers."""
    port = port if port is not None else _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name=f"serve-asgi-{port}", daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_ready(server, thread, url)
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=_SHUTDOWN_TIMEOUT_S)


def _wait_until_ready(server: uvicorn.Server, thread: threading.Thread, url: str) -> None:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if not thread.is_alive():
            raise RuntimeError(f"ASGI server on {url} exited during startup")
        if server.started:
            try:
                httpx.get(url + "/", timeout=2.0, trust_env=False)
                return
            except httpx.TransportError:
                pass
        time.sleep(0.02)
    raise TimeoutError(f"ASGI server on {url} did not become ready in {_STARTUP_TIMEOUT_S}s")
