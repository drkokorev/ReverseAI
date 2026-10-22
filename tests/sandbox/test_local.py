import socket
import sys
import time

import httpx
import pytest

from reverseai.sandbox import LocalSandbox, RunResult, free_port


def test_local_run_scrubs_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    r = LocalSandbox(tmp_path).run(
        ["python", "-c", "import os;print(os.environ.get('ANTHROPIC_API_KEY'))"]
    )
    assert r.exit_code == 0
    assert r.stdout.strip() == "None"


def test_local_env_allowlist_and_unbuffered(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_VAR", "x")
    monkeypatch.setenv("LANG", "C")
    sb = LocalSandbox(tmp_path, env_allowlist=("PATH", "LANG"))
    r = sb.run(
        ["python", "-c", "import os;print(os.environ.get('MY_VAR'), os.environ.get('LANG'), os.environ.get('PYTHONUNBUFFERED'))"]
    )
    assert r.stdout.split() == ["None", "C", "1"]


def test_local_python_uses_current_interpreter(tmp_path):
    r = LocalSandbox(tmp_path).run(["python", "-c", "import sys;print(sys.executable)"])
    assert r.stdout.strip() == sys.executable


def test_local_runs_in_workdir(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi from workdir')")
    r = LocalSandbox(tmp_path).run(["python", "hello.py"])
    assert r.stdout.strip() == "hi from workdir"


def test_local_not_isolated(tmp_path):
    assert LocalSandbox(tmp_path).isolated is False


def test_local_nonzero_exit_and_stderr(tmp_path):
    r = LocalSandbox(tmp_path).run(["python", "-c", "import sys;sys.stderr.write('boom');sys.exit(3)"])
    assert r.exit_code == 3
    assert r.stderr == "boom"
    assert r.timed_out is False


def test_local_missing_command(tmp_path):
    r = LocalSandbox(tmp_path).run(["definitely-not-a-command-xyz"])
    assert r.exit_code != 0
    assert r.timed_out is False
    assert "definitely-not-a-command-xyz" in r.stderr


def test_local_timeout(tmp_path):
    t0 = time.monotonic()
    r = LocalSandbox(tmp_path).run(["python", "-c", "import time;time.sleep(5)"], timeout=0.5)
    assert r.timed_out is True
    assert r.exit_code != 0
    assert time.monotonic() - t0 < 4


def test_local_timeout_kills_children(tmp_path):
    code = (
        "import subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        "print(p.pid,flush=True);time.sleep(30)"
    )
    r = LocalSandbox(tmp_path).run(["python", "-c", code], timeout=1)
    assert r.timed_out is True
    pid = int(r.stdout.split()[0])
    import os

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail("child process survived timeout")


def test_local_output_truncated_to_tail(tmp_path):
    r = LocalSandbox(tmp_path).run(
        ["python", "-c", "print('a'*300000);print('END')"]
    )
    assert len(r.stdout) <= 200_000
    assert r.stdout.rstrip().endswith("END")


def test_run_result_tail():
    r = RunResult(exit_code=1, stdout="o1\no2\no3", stderr="e1\ne2", timed_out=False)
    assert r.tail(2) == "e1\ne2"
    assert r.tail(3) == "o3\ne1\ne2"
    assert r.tail(100) == "o1\no2\no3\ne1\ne2"
    assert RunResult(0, "", "", False).tail() == ""


def _port_is_free(port: int) -> bool:
    """True if nothing is listening on the port (connection refused)."""
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def test_free_port():
    p = free_port()
    assert 0 < p < 65536
    assert _port_is_free(p)


def test_local_start_service(tmp_path):
    (tmp_path / "index.html").write_text("ok")
    port = free_port()
    sb = LocalSandbox(tmp_path)
    handle = sb.start(
        ["python", "-m", "http.server", str(port), "--bind", "127.0.0.1"], port=port
    )
    try:
        assert handle.base_url == f"http://127.0.0.1:{port}"
        r = httpx.get(handle.base_url)
        assert r.status_code == 200
    finally:
        handle.stop()
    assert _port_is_free(port)
    handle.stop()  # idempotent


def test_local_start_ready_on_error_status(tmp_path):
    port = free_port()
    handle = LocalSandbox(tmp_path).start(
        ["python", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        port=port,
        ready_path="/missing",
    )
    try:
        assert httpx.get(handle.base_url + "/missing").status_code == 404
    finally:
        handle.stop()


def test_local_start_timeout_cleans_up(tmp_path):
    (tmp_path / "pid.txt").write_text("")
    code = "import os,time;open('pid.txt','w').write(str(os.getpid()));time.sleep(60)"
    port = free_port()
    with pytest.raises(TimeoutError):
        LocalSandbox(tmp_path).start(["python", "-c", code], port=port, timeout=1)
    import os

    pid = int((tmp_path / "pid.txt").read_text())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail("process survived readiness timeout")


def test_local_start_process_exits_early(tmp_path):
    port = free_port()
    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="exited"):
        LocalSandbox(tmp_path).start(
            ["python", "-c", "import sys;print('bad config');sys.exit(2)"], port=port, timeout=20
        )
    assert time.monotonic() - t0 < 10


def test_wait_ready_ignores_proxy_settings_of_the_environment(monkeypatch):
    from fastapi import FastAPI

    from reverseai.bench.server import serve_asgi
    from reverseai.sandbox.base import wait_ready

    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # nothing listens there
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    with serve_asgi(FastAPI()) as url:
        wait_ready(url, "/", 3.0, exited=lambda: False, diagnostics=lambda: "")


def test_a_second_stop_never_signals_a_reaped_process_group(tmp_path, monkeypatch):
    import os

    port = free_port()
    handle = LocalSandbox(tmp_path).start(
        ["python", "-m", "http.server", str(port), "--bind", "127.0.0.1"], port=port
    )
    handle.stop()
    signalled: list[int] = []
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signalled.append(pid))
    handle.stop()  # the pid may belong to another process group by now
    assert signalled == []
