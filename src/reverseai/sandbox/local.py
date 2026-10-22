"""Sandbox that runs commands as local subprocesses with a scrubbed environment.

Not isolated: filesystem and network are the host's. Use only for trusted-enough code.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from reverseai.sandbox.base import (
    STOP_GRACE_S,
    RunResult,
    ServiceHandle,
    read_tail,
    wait_ready,
)


def _kill_group(pid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, sig)


class LocalSandbox:
    isolated = False

    def __init__(
        self,
        workdir: Path,
        env_allowlist: tuple[str, ...] = ("PATH", "HOME", "LANG", "PYTHONPATH"),
    ) -> None:
        self.workdir = Path(workdir)
        self.env_allowlist = env_allowlist

    def _env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in self.env_allowlist if k in os.environ}
        env["PYTHONUNBUFFERED"] = "1"
        return env

    @staticmethod
    def _resolve(cmd: list[str]) -> list[str]:
        if cmd and cmd[0] == "python":
            return [sys.executable, *cmd[1:]]
        return list(cmd)

    def _popen(self, cmd: list[str], out, err) -> subprocess.Popen:
        return subprocess.Popen(
            self._resolve(cmd),
            cwd=self.workdir,
            env=self._env(),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,  # own process group so children die with the parent
        )

    def run(self, cmd: list[str], *, timeout: float = 600) -> RunResult:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                proc = self._popen(cmd, out, err)
            except OSError as e:
                return RunResult(127, "", f"cannot execute {cmd[:1]}: {e}", False)
            timed_out = False
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc.pid, signal.SIGKILL)
                proc.wait()
            else:
                _kill_group(proc.pid, signal.SIGKILL)  # reap stray background children
            return RunResult(proc.returncode, read_tail(out), read_tail(err), timed_out)

    def start(
        self, cmd: list[str], *, port: int, ready_path: str = "/", timeout: float = 30
    ) -> ServiceHandle:
        log = tempfile.TemporaryFile()  # noqa: SIM115 - closed by stop()
        try:
            proc = self._popen(cmd, log, subprocess.STDOUT)
        except OSError as e:
            log.close()
            raise RuntimeError(f"cannot execute {cmd[:1]}: {e}") from e

        stopped = False

        def stop() -> None:
            nonlocal stopped
            if stopped:  # the group is reaped: its pid may name another process group now
                return
            stopped = True
            if proc.poll() is None:
                _kill_group(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=STOP_GRACE_S)
                except subprocess.TimeoutExpired:
                    pass
            _kill_group(proc.pid, signal.SIGKILL)
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
