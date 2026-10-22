"""Sandbox that runs commands in a Docker container.

``run`` has no network at all. ``start`` uses the default bridge network with the
service port published on 127.0.0.1 only; use it after implementation (spec §6.6).
The service must listen on 0.0.0.0 inside the container to be reachable.
"""

from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

from reverseai.sandbox.base import (
    STOP_GRACE_S,
    RunResult,
    ServiceHandle,
    read_tail,
    wait_ready,
)


def _rm_container(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30, check=False)


class DockerSandbox:
    isolated = True

    def __init__(self, workdir: Path, image: str = "python:3.12-slim") -> None:
        self.workdir = Path(workdir)
        self.image = image

    def _docker_run(self, name: str, extra: list[str], cmd: list[str]) -> list[str]:
        return [
            "docker", "run", "--rm", "--name", name,
            *extra,
            "-v", f"{self.workdir.resolve()}:/work", "-w", "/work",
            "-e", "PYTHONUNBUFFERED=1",
            self.image, *cmd,
        ]  # fmt: skip

    def run(self, cmd: list[str], *, timeout: float = 600) -> RunResult:
        name = f"reverseai-run-{uuid.uuid4().hex[:12]}"
        argv = self._docker_run(name, ["--network", "none"], cmd)
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                proc = subprocess.Popen(
                    argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err
                )
            except OSError as e:
                return RunResult(127, "", f"cannot execute docker: {e}", False)
            timed_out = False
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _rm_container(name)  # killing the client alone would leave the container running
                proc.kill()
                proc.wait()
            return RunResult(proc.returncode, read_tail(out), read_tail(err), timed_out)

    def start(
        self, cmd: list[str], *, port: int, ready_path: str = "/", timeout: float = 30
    ) -> ServiceHandle:
        name = f"reverseai-svc-{uuid.uuid4().hex[:12]}"
        argv = self._docker_run(name, ["-p", f"127.0.0.1:{port}:{port}"], cmd)
        log = tempfile.TemporaryFile()  # noqa: SIM115 - closed by stop()
        try:
            proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT
            )
        except OSError as e:
            log.close()
            raise RuntimeError(f"cannot execute docker: {e}") from e

        def stop() -> None:
            _rm_container(name)
            try:
                proc.wait(timeout=STOP_GRACE_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if not log.closed:
                log.close()

        base_url = f"http://127.0.0.1:{port}"
        try:
            wait_ready(
                base_url,
                ready_path,
                timeout,
                exited=lambda: proc.poll() is not None,
                diagnostics=lambda: read_tail(log, 4000),
            )
        except BaseException:
            stop()
            raise
        return ServiceHandle(base_url=base_url, stop=stop)
