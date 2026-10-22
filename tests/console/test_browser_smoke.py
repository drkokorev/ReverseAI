"""Browser smoke test: the console under uvicorn, every page in both themes, the release flow.

Set CONSOLE_SCREENSHOTS_DIR to also save full-page screenshots of every page in both themes
(that is how docs/console-screenshots/ is produced).
"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from reverseai.bench.server import serve_asgi
from reverseai.console import create_app
from reverseai.sandbox import LocalSandbox

pytestmark = pytest.mark.browser

DONE = "console-demo"  # audited: every phase completed
FLOW = "console-flow"  # spec completed: prepare-release and approval happen in the browser
BACKGROUNDS = {"dark": "rgb(0, 0, 0)", "light": "rgb(250, 250, 250)"}
PAGES = {
    "projects": "/",
    "new-project": "/projects/new",
    "overview": f"/projects/{DONE}",
    "release": f"/projects/{DONE}/release",
    "release-scenarios": f"/projects/{DONE}/release?tab=scenarios",
    "release-cleanup": f"/projects/{DONE}/release?tab=cleanup",
    "parity": f"/projects/{DONE}/parity",
    "costs": f"/projects/{DONE}/costs",
    "flow-overview": f"/projects/{FLOW}",
}
SCREENSHOTS = os.environ.get("CONSOLE_SCREENSHOTS_DIR")
# Optional: a dedicated directory for the demo projects while screenshots are taken (a neutral
# path keeps pytest temp paths out of the published images). Its `projects/` child is recreated.
DEMO_ROOT = os.environ.get("CONSOLE_DEMO_ROOT")


@pytest.fixture
def console_url(snapshots, scripted_gateway, tmp_path) -> Iterator[str]:
    if SCREENSHOTS and DEMO_ROOT:
        root = Path(DEMO_ROOT).expanduser() / "projects"
        shutil.rmtree(root, ignore_errors=True)
    else:
        root = tmp_path / "projects"
    shutil.copytree(snapshots["audited"], root)
    shutil.copytree(snapshots["specced"] / DONE, root / FLOW)
    card_path = root / FLOW / "card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["name"] = "Console Flow"
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    app = create_app(root, gateway_factory=scripted_gateway, sandbox_factory=LocalSandbox,
                     operator="Даниил Кокорев")
    with serve_asgi(app) as url:
        yield url


@pytest.fixture
def browser() -> Iterator:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        chromium = p.chromium.launch()
        try:
            yield chromium
        finally:
            chromium.close()


def _open(browser, scheme: str, width: int = 1440):
    context = browser.new_context(color_scheme=scheme, viewport={"width": width, "height": 900},
                                  accept_downloads=True)
    page = context.new_page()
    messages: list[str] = []
    page.on("console", lambda m: messages.append(m.text))
    return context, page, messages


def _background(page) -> str:
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def _shot(page, name: str) -> None:
    if SCREENSHOTS:
        path = Path(SCREENSHOTS) / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=True)


def _no_csp_violations(messages: list[str]) -> None:
    blocked = [m for m in messages if "Content Security Policy" in m]
    assert not blocked, blocked


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_every_page_renders_in_both_themes(browser, console_url, scheme) -> None:
    context, page, messages = _open(browser, scheme)
    try:
        for name, path in PAGES.items():
            response = page.goto(console_url + path)
            assert response is not None and response.ok, path
            page.wait_for_load_state("networkidle")
            assert _background(page) == BACKGROUNDS[scheme], path
            assert page.locator("header .wordmark").inner_text() == "REVERSEAI"
            _shot(page, f"{name}-{scheme}")
        _no_csp_violations(messages)
    finally:
        context.close()


def test_phone_width_has_no_horizontal_page_scroll(browser, console_url) -> None:
    context, page, _ = _open(browser, "dark", width=375)
    try:
        for name in ("overview", "release", "parity", "projects"):
            page.goto(console_url + PAGES[name])
            page.wait_for_load_state("networkidle")
            overflow = page.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow <= 0, name
            _shot(page, f"phone-{name}-dark")
    finally:
        context.close()


def test_theme_toggle_is_remembered(browser, console_url) -> None:
    from playwright.sync_api import expect

    context, page, _ = _open(browser, "dark")
    try:
        page.goto(console_url + "/")
        assert _background(page) == BACKGROUNDS["dark"]
        page.click("[data-theme-toggle]")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.reload()
        assert page.evaluate("document.documentElement.dataset.theme") == "light"
        assert _background(page) == BACKGROUNDS["light"]
    finally:
        context.close()


def test_release_tabs_switch_without_reload(browser, console_url) -> None:
    context, page, _ = _open(browser, "light")
    try:
        page.goto(console_url + PAGES["release"])
        assert page.locator("#tab-scenarios").is_hidden()
        page.click('[data-tab="scenarios"]')
        assert page.locator("#tab-scenarios").is_visible()
        assert page.locator("#tab-spec").is_hidden()
        assert page.url.endswith("?tab=scenarios")
    finally:
        context.close()


def test_prepare_release_approve_and_download_evidence(browser, console_url, tmp_path) -> None:
    context, page, messages = _open(browser, "dark")
    try:
        # prepare-release as a background job; the page polls and reloads when it finishes
        page.goto(console_url + f"/projects/{FLOW}")
        page.click(f'form[action="/projects/{FLOW}/run/prepare-release"] button[type="submit"]')
        page.wait_for_selector('#job[data-job-status="succeeded"]', timeout=60_000)
        assert "SHA-256 пакета" in page.locator(".job-log").inner_text()

        # review and approve
        page.goto(console_url + f"/projects/{FLOW}/release")
        approve = page.locator("[data-confirm-submit]")
        assert approve.is_disabled()  # until the confirmation box is checked
        page.fill('input[name="approver"]', "Анна Аналитик")
        page.select_option('select[name="role"]', "customer_analyst")
        page.check('input[name="confirm"]')
        assert approve.is_enabled()
        approve.click()
        page.wait_for_selector("text=ВЫПУЩЕНО")
        assert "Анна Аналитик" in page.content()
        _shot(page, "release-approved-dark")

        # download the evidence pack of the audited project
        page.goto(console_url + PAGES["parity"])
        with page.expect_download() as download_info:
            page.click('a[href$="/evidence.zip"]')
        download = download_info.value
        assert download.suggested_filename == "evidence_console-demo.zip"
        saved = tmp_path / download.suggested_filename
        download.save_as(saved)
        with zipfile.ZipFile(saved) as archive:
            assert "README.md" in archive.namelist()
        _no_csp_violations(messages)
    finally:
        context.close()
