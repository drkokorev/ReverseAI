import functools
import subprocess
from pathlib import Path

import pytest

DOCKER_TEST_IMAGE = "python:3.12-slim"


def _succeeds(cmd: list[str]) -> bool:
    try:
        r = subprocess.run(cmd, check=False, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


@functools.lru_cache(maxsize=1)
def docker_skip_reason() -> str | None:
    """Why `docker` tests cannot run here, or None if they can."""
    if not _succeeds(["docker", "info"]):
        return "Docker daemon is not available (`docker info` failed)"
    if not _succeeds(["docker", "image", "inspect", DOCKER_TEST_IMAGE]):
        # never pull implicitly from a test run
        return f"image {DOCKER_TEST_IMAGE} is not present locally (run `docker pull {DOCKER_TEST_IMAGE}`)"
    return None


@functools.lru_cache(maxsize=1)
def browser_skip_reason() -> str | None:
    """Why `browser` tests cannot run here, or None if they can."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            if Path(p.chromium.executable_path).exists():
                return None
    except Exception as exc:  # noqa: BLE001 - any failure means "cannot run browser tests"
        return f"playwright unavailable: {exc}"
    return "Playwright Chromium is not installed (run `uv run playwright install chromium`)"


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("browser"):
        reason = browser_skip_reason()
        if reason:
            pytest.skip(reason)
    if item.get_closest_marker("docker"):
        reason = docker_skip_reason()
        if reason:
            pytest.skip(reason)
