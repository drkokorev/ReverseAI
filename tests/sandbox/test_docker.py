import httpx
import pytest

from reverseai.sandbox import DockerSandbox, free_port

pytestmark = pytest.mark.docker


def test_docker_isolated_flag(tmp_path):
    assert DockerSandbox(tmp_path).isolated is True


def test_docker_runs_in_mounted_workdir(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi from container')")
    r = DockerSandbox(tmp_path).run(["python", "hello.py"])
    assert r.exit_code == 0
    assert r.stdout.strip() == "hi from container"


def test_docker_has_no_network(tmp_path):
    r = DockerSandbox(tmp_path).run(
        ["python", "-c", "import urllib.request;urllib.request.urlopen('http://example.com', timeout=5)"]
    )
    assert r.exit_code != 0


def test_docker_timeout_removes_container(tmp_path):
    r = DockerSandbox(tmp_path).run(["python", "-c", "import time;time.sleep(30)"], timeout=3)
    assert r.timed_out is True


def test_docker_start_service(tmp_path):
    (tmp_path / "index.html").write_text("ok")
    port = free_port()
    handle = DockerSandbox(tmp_path).start(
        ["python", "-m", "http.server", str(port), "--bind", "0.0.0.0"], port=port, timeout=60
    )
    try:
        assert httpx.get(handle.base_url).status_code == 200
    finally:
        handle.stop()
