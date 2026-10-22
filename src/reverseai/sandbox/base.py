"""Sandbox contract and helpers shared by the local and docker implementations."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

import httpx

MAX_CAPTURE_CHARS = 200_000
_READ_BYTES = MAX_CAPTURE_CHARS * 4  # enough bytes to cover MAX_CAPTURE_CHARS of any UTF-8 text
STOP_GRACE_S = 3.0


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool

    def tail(self, n: int = 60) -> str:
        """Last ``n`` lines of stdout followed by stderr, combined."""
        lines = self.stdout.splitlines() + self.stderr.splitlines()
        return "\n".join(lines[-n:]) if n > 0 else ""


@dataclass(frozen=True)
class ServiceHandle:
    base_url: str
    stop: Callable[[], None]


class Sandbox(Protocol):
    workdir: Path
    isolated: bool

    def run(self, cmd: list[str], *, timeout: float = 600) -> RunResult: ...

    def start(
        self, cmd: list[str], *, port: int, ready_path: str = "/", timeout: float = 30
    ) -> ServiceHandle: ...


def free_port() -> int:
    """Ask the OS for a currently unused TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def read_tail(f: IO[bytes], max_chars: int = MAX_CAPTURE_CHARS) -> str:
    """Last ``max_chars`` characters of a binary file, decoded leniently."""
    f.flush()
    size = f.seek(0, 2)
    f.seek(max(0, size - _READ_BYTES))
    return f.read().decode("utf-8", errors="replace")[-max_chars:]


def wait_ready(
    base_url: str,
    ready_path: str,
    timeout: float,
    *,
    exited: Callable[[], bool],
    diagnostics: Callable[[], str],
) -> None:
    """Poll ``base_url + ready_path`` until any HTTP response arrives.

    Raises RuntimeError if the service process exits first, TimeoutError on timeout.
    """
    url = base_url + (ready_path if ready_path.startswith("/") else "/" + ready_path)
    deadline = time.monotonic() + timeout
    while True:
        if exited():
            raise RuntimeError(f"service exited before becoming ready:\n{diagnostics()}")
        try:
            httpx.get(url, timeout=1.0, trust_env=False)  # local service: never via a proxy
            return
        except httpx.HTTPError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError(f"service at {url} not ready after {timeout}s:\n{diagnostics()}")
        time.sleep(0.1)
