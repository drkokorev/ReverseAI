"""Headless-browser exploration of a target web app.

The explorer crawls same-domain pages with Chromium, records every network exchange as an
embedded HAR and stores everything it sees in the dirty zone. Page JS/CSS/HTML is kept verbatim
as `expression`/`document` artifacts and is never interpreted (D-005).
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, Route, WebSocketRoute, sync_playwright
from pydantic import BaseModel

from reverseai.observe.har import parse_har
from reverseai.project import IntakeError, ProjectCard
from reverseai.zones.store import ArtifactStore, Zone

_ACTOR = "observer"
_TEXT_EXCERPT_CHARS = 2000
_MAX_BUTTONS = 50
_ACTION_TIMEOUT_MS = 5_000
_NAVIGATION_TIMEOUT_MS = 30_000
_SETTLE_QUIET_S = 0.5
_SETTLE_TIMEOUT_S = 10.0
_STATIC_SUFFIXES = (
    ".js", ".mjs", ".css", ".map", ".wasm",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".webm", ".ogg", ".wav",
)  # fmt: skip
_SKIPPED_FIELD_TYPES = {"hidden", "submit", "button", "reset", "image", "file", "password"}
_CONTROL_SELECTOR = (
    "button, input[type=button], input[type=checkbox], [role=button], [role=checkbox]"
)
_LABEL_CHARS = 80
# Labels of controls that look like they destroy or discard something (record, session, input).
_DESTRUCTIVE_RE = re.compile(
    r"\b(?:delete|remove|destroy|erase|discard|purge|trash|clear|reset|drop\b|archive|revoke"
    r"|log ?out|sign ?out|unsubscribe|cancel)|удал|очист|сброс|выйти|отмен"
    r"|^\s*[x×✕✖🗑]\s*$",
    re.IGNORECASE,
)

# Describes every element matched by _CONTROL_SELECTOR, in locator order. Controls inside or
# owned by a form are left to form submission; hidden or disabled ones cannot be clicked.
_DESCRIBE_CONTROLS_JS = """(els) => els.map((el) => {
  const owned = el.closest('form') || el.hasAttribute('form');
  const visible = el.getClientRects().length > 0
    && getComputedStyle(el).visibility !== 'hidden';
  const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
  const label = (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText
    || el.value || '').trim().replace(/\\s+/g, ' ');
  return {
    clickable: !owned && visible && !disabled,
    tag: el.tagName.toLowerCase(),
    type: (el.getAttribute('type') || '').toLowerCase(),
    role: (el.getAttribute('role') || '').toLowerCase(),
    label: label,
  };
})"""

_EXTRACT_JS = """() => {
  const labelFor = (el) => {
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l) return l.innerText.trim();
    }
    const parent = el.closest('label');
    if (parent) return parent.innerText.trim();
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || null;
  };
  const forms = Array.from(document.forms).map((f) => {
    const seen = new Set();
    const fields = [];
    for (const e of f.querySelectorAll('input, select, textarea')) {
      const type = e.tagName === 'SELECT' ? 'select'
        : e.tagName === 'TEXTAREA' ? 'textarea' : (e.type || 'text');
      if (!e.name || ['submit', 'button', 'reset', 'image'].includes(type)) continue;
      const key = e.name + '|' + type;
      if (seen.has(key)) continue;
      seen.add(key);
      fields.push({name: e.name, type: type, required: !!e.required, label: labelFor(e)});
    }
    return {
      action: new URL(f.getAttribute('action') || '', document.baseURI).href,
      method: (f.getAttribute('method') || 'get').toUpperCase(),
      fields: fields,
    };
  });
  const buttons = Array.from(
    document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]')
  ).map((b) => (b.innerText || b.value || b.getAttribute('aria-label') || '').trim())
   .filter(Boolean);
  return {
    title: document.title || '',
    links: Array.from(document.querySelectorAll('a[href]')).map((a) => a.href),
    forms: forms,
    buttons: buttons,
    text: document.body ? document.body.innerText : '',
  };
}"""


class FormField(BaseModel):
    name: str
    type: str
    required: bool
    label: str | None


class FormInfo(BaseModel):
    action: str
    method: str
    fields: list[FormField]


class PageObservation(BaseModel):
    url: str
    title: str
    links: list[str]
    forms: list[FormInfo]
    buttons: list[str]
    text_excerpt: str
    screenshot_ref: str | None


class ClickRecord(BaseModel):
    """One click on a non-form control: the page it was on and how the control looked."""

    page: str
    control: str
    destructive: bool


class ExplorerConfig(BaseModel):
    start_url: str
    allowed_domains: list[str]
    max_pages: int = 50
    delay_s: float = 0.5
    submit_forms: bool = False
    # Clicks on non-form controls (buttons, checkboxes) over the whole crawl. Only a sandbox
    # target (card.target_is_sandbox) is ever clicked; 0 disables clicking.
    max_clicks: int = 50  # attempts, so a control whose click keeps failing cannot loop


class ExplorationResult(BaseModel):
    pages: list[PageObservation]
    har_ref: str
    expression_refs: list[str]
    skipped: list[str] = []
    clicks: list[ClickRecord] = []


def _hostname(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _followable(url: str, allowed: set[str]) -> str | None:
    """Normalized (fragment-free) URL if it is an in-domain http(s) page link, else None."""
    url = urldefrag(url)[0]
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in allowed:
        return None
    if parts.path.lower().endswith(_STATIC_SUFFIXES):
        return None
    return url


def _in_scope(url: str, allowed: set[str]) -> bool:
    """True for http(s) URLs whose host is in `allowed` (any path, static or not)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and (parts.hostname or "").lower() in allowed


_SAFE_METHODS = frozenset({"GET", "HEAD"})


def _scope_router(
    allowed: set[str], skipped: list[str], *, allow_writes: bool
) -> Callable[[Route], None]:
    """Route handler: abort every http(s) request whose host is outside `allowed`.

    Without `allow_writes` (the target is not a sandbox), in-scope requests other than GET/HEAD
    (e.g. a POST fired by the page's own JS) are aborted too and recorded as "METHOD url".
    """

    def handle(route: Route) -> None:
        url = route.request.url
        if urlsplit(url).scheme not in ("http", "https"):
            route.continue_()
        elif not _in_scope(url, allowed):
            if url not in skipped:
                skipped.append(url)
            route.abort()
        elif not allow_writes and route.request.method.upper() not in _SAFE_METHODS:
            entry = f"{route.request.method.upper()} {url}"
            if entry not in skipped:
                skipped.append(entry)
            route.abort()
        else:
            route.continue_()

    return handle


def _ws_in_scope(url: str, allowed: set[str]) -> bool:
    """True for ws(s) URLs whose host is in `allowed`."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("ws", "wss") and (parts.hostname or "").lower() in allowed


def _websocket_router(allowed: set[str], skipped: list[str]) -> Callable[[WebSocketRoute], None]:
    """WebSocket handler: `context.route` never sees WebSockets, so they are routed here.

    An in-scope socket is connected to the target as usual (messages pass through); any other
    is never connected (Playwright keeps it as a mock with no server behind it, so nothing
    leaves the browser) and is recorded in `skipped`. `WebSocketRoute.close()` is not called:
    in the sync API it blocks forever inside a route handler.
    """

    def handle(ws: WebSocketRoute) -> None:
        if _ws_in_scope(ws.url, allowed):
            ws.connect_to_server()
        elif ws.url not in skipped:
            skipped.append(ws.url)

    return handle


def _check_scope(config: ExplorerConfig, card: ProjectCard) -> set[str]:
    if config.submit_forms and not card.target_is_sandbox:
        raise IntakeError("submit_forms_needs_sandbox")
    allowed = {d.lower() for d in config.allowed_domains}
    if not allowed <= {d.lower() for d in card.allowed_domains}:
        raise IntakeError("explorer_domains_subset")
    if _hostname(config.start_url) not in allowed:
        raise IntakeError("start_host_not_allowed", host=_hostname(config.start_url))
    return allowed


def _fill_value(field: FormField, counter: int) -> str | None:
    kind = field.type
    if kind in _SKIPPED_FIELD_TYPES:
        return None
    if kind == "email":
        return f"sample{counter}@example.com"
    if kind == "url":
        return f"https://example.com/{counter}"
    if kind in ("number", "range"):
        return "1"
    if kind == "tel":
        return "5550100"
    if kind == "date":
        return "2026-01-01"
    return f"Sample {counter}"


class _NetworkTracker:
    """Counts in-flight requests so we can wait for traffic triggered by a click.

    `page.wait_for_load_state("networkidle")` returns at once when the page already reached
    that state, so it cannot wait for fetches started by a JS submit handler.
    """

    def __init__(self, page: Page) -> None:
        self.inflight = 0
        self.last_event = time.monotonic()
        page.on("request", lambda _r: self._start())
        page.on("requestfinished", lambda _r: self._end())
        page.on("requestfailed", lambda _r: self._end())

    def _start(self) -> None:
        self.inflight += 1
        self.last_event = time.monotonic()

    def _end(self) -> None:
        self.inflight = max(0, self.inflight - 1)
        self.last_event = time.monotonic()

    def settle(self, page: Page) -> None:
        """Wait until no request is in flight and none started or ended for the quiet period."""
        self.last_event = time.monotonic()
        deadline = self.last_event + _SETTLE_TIMEOUT_S
        while time.monotonic() < deadline:
            quiet = time.monotonic() - self.last_event
            if self.inflight == 0 and quiet >= _SETTLE_QUIET_S:
                return
            page.wait_for_timeout(50)


def _fill_and_submit(
    page: Page,
    tracker: _NetworkTracker,
    index: int,
    form: FormInfo,
    counter: int,
    delay_s: float,
    sleep: Callable[[float], None],
) -> int:
    """Fill form number `index` with synthetic values and submit it once. Returns the new counter."""
    form_loc = page.locator("form").nth(index)
    first_text: Locator | None = None
    for field in form.fields:
        loc = form_loc.locator(f"[name={json.dumps(field.name)}]").first
        try:
            if field.type in ("checkbox", "radio"):
                loc.check()
            elif field.type == "select":
                loc.select_option(index=0)
            else:
                value = _fill_value(field, counter)
                if value is None:
                    continue
                counter += 1
                loc.fill(value)
                first_text = first_text or loc
        except PlaywrightError:
            continue
    sleep(delay_s)
    try:
        submit = form_loc.locator(
            "button[type=submit], input[type=submit], button:not([type])"
        ).first
        if submit.count():
            submit.click()
        elif first_text is not None:
            first_text.press("Enter")
        else:
            return counter
        tracker.settle(page)
    except PlaywrightError:
        pass
    return counter


def _control_key(control: dict[str, Any]) -> tuple[str, str, str, str]:
    """What makes two controls "the same": rows of a list share one key and get one click."""
    return (control["tag"], control["type"], control["role"], control["label"][:_LABEL_CHARS])


def _describe(control: dict[str, Any]) -> str:
    kind = control["role"] or (
        f"{control['tag']}[{control['type']}]" if control["type"] else control["tag"]
    )
    return f"{kind} {control['label'][:_LABEL_CHARS]!r}"


def _click_controls(
    page: Page,
    tracker: _NetworkTracker,
    page_url: str,
    budget: int,
    delay_s: float,
    sleep: Callable[[float], None],
) -> tuple[int, list[ClickRecord], list[str]]:
    """Click each distinct non-form control of `page_url` once, re-reading the DOM after each.

    Makes at most `budget` attempts. Returns the attempts made, the clicks that succeeded and
    the URLs clicks navigated to; after a navigation the page is reloaded at `page_url`.
    """
    clicked: set[tuple[str, str, str, str]] = set()
    clicks: list[ClickRecord] = []
    reached: list[str] = []
    attempts = 0
    controls = page.locator(_CONTROL_SELECTOR)
    while attempts < budget:
        try:
            described: list[dict[str, Any]] = controls.evaluate_all(_DESCRIBE_CONTROLS_JS)
        except PlaywrightError:
            break
        target = next(
            (
                (index, control)
                for index, control in enumerate(described)
                if control["clickable"] and _control_key(control) not in clicked
            ),
            None,
        )
        if target is None:
            break
        index, control = target
        clicked.add(_control_key(control))
        record = ClickRecord(
            page=page_url,
            control=_describe(control),
            destructive=bool(_DESTRUCTIVE_RE.search(control["label"])),
        )
        attempts += 1
        sleep(delay_s)
        try:
            controls.nth(index).click()
        except PlaywrightError:
            continue
        clicks.append(record)
        tracker.settle(page)
        landed = urldefrag(page.url)[0]
        if landed != page_url:
            reached.append(landed)
            sleep(delay_s)  # going back is one more request toward the target
            try:
                page.goto(page_url, wait_until="load")
                tracker.settle(page)
            except PlaywrightError:
                break
    return attempts, clicks, reached


def _observe(page: Page, screenshot_ref: str | None, allowed: set[str]) -> PageObservation:
    raw: dict[str, Any] = page.evaluate(_EXTRACT_JS)
    links: list[str] = []
    for href in raw["links"]:
        link = _followable(href, allowed)
        if link is not None and link not in links:
            links.append(link)
    buttons = list(dict.fromkeys(raw["buttons"]))[:_MAX_BUTTONS]
    return PageObservation(
        url=page.url,
        title=raw["title"],
        links=links,
        forms=[FormInfo.model_validate(f) for f in raw["forms"]],
        buttons=buttons,
        text_excerpt=raw["text"][:_TEXT_EXCERPT_CHARS],
        screenshot_ref=screenshot_ref,
    )


def _crawl(
    page: Page,
    config: ExplorerConfig,
    store: ArtifactStore,
    allowed: set[str],
    sleep: Callable[[float], None],
    skipped: list[str],
    clicks: list[ClickRecord],
    *,
    may_click: bool,
) -> list[PageObservation]:
    """Breadth-first crawl; `may_click` (sandbox targets only) also clicks non-form controls."""
    pages: list[PageObservation] = []
    click_budget = config.max_clicks
    queue: deque[str] = deque([urldefrag(config.start_url)[0]])
    visited: set[str] = set(queue)
    submitted: set[tuple[str, str, tuple[str, ...]]] = set()
    counter = 1
    navigations = 0
    tracker = _NetworkTracker(page)

    while queue and len(pages) < config.max_pages:
        url = queue.popleft()
        if navigations:
            sleep(config.delay_s)
        navigations += 1
        try:
            response = page.goto(url, wait_until="load")
            tracker.settle(page)
        except PlaywrightError:
            skipped.append(url)
            continue
        content_type = (response.header_value("content-type") if response else "") or ""
        if "html" not in content_type.lower():
            skipped.append(url)
            continue
        final_url = urldefrag(page.url)[0]
        visited.add(final_url)
        if _followable(final_url, allowed) is None:
            skipped.append(url)  # redirected out of scope
            continue

        try:
            png = page.screenshot(full_page=True)
            shot = store.put(Zone.DIRTY, "screenshot", final_url, png, meta={"url": final_url})
            observation = _observe(page, shot.id, allowed)
        except PlaywrightError:  # e.g. the page navigated away while it was being read
            skipped.append(url)
            continue
        store.put_json(Zone.DIRTY, "page", final_url, observation.model_dump(mode="json"))
        pages.append(observation)

        for link in observation.links:
            if link not in visited:
                visited.add(link)
                queue.append(link)

        if config.submit_forms:
            for index, form in enumerate(observation.forms):
                signature = (form.action, form.method, tuple(f.name for f in form.fields))
                if signature in submitted:
                    continue
                if not _in_scope(form.action, allowed):
                    skipped.append(form.action)
                    submitted.add(signature)
                    continue
                submitted.add(signature)
                counter = _fill_and_submit(
                    page, tracker, index, form, counter, config.delay_s, sleep
                )
                if urldefrag(page.url)[0] != final_url:
                    sleep(config.delay_s)  # going back is one more request toward the target
                    try:
                        page.goto(final_url, wait_until="load")
                        tracker.settle(page)
                    except PlaywrightError:
                        break

        if may_click and click_budget > 0 and urldefrag(page.url)[0] == final_url:
            attempts, made, reached = _click_controls(
                page, tracker, final_url, click_budget, config.delay_s, sleep
            )
            click_budget -= attempts
            clicks.extend(made)
            for landed in reached:
                link = _followable(landed, allowed)
                if link is not None and link not in visited:
                    visited.add(link)
                    queue.append(link)
    return pages


def _close_popup(popup: Page, main: Page, skipped: list[str]) -> None:
    if popup is main:
        return
    skipped.append(f"popup {popup.url}")
    try:
        popup.close()
    except PlaywrightError:
        pass


def explore(
    config: ExplorerConfig,
    card: ProjectCard,
    store: ArtifactStore,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> ExplorationResult:
    """Crawl `config.start_url` breadth-first within the allowed domains.

    Writes the HAR (`har`), pages (`page`), full-page PNG screenshots (`screenshot`),
    and the target's own JS/CSS/HTML (`expression` / `document`) to the dirty zone.
    """
    allowed = _check_scope(config, card)
    skipped: list[str] = []
    clicks: list[ClickRecord] = []
    may_click = card.target_is_sandbox and config.max_clicks > 0

    with tempfile.TemporaryDirectory(prefix="reverseai-har-") as tmp:
        har_path = Path(tmp) / "session.har"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    record_har_path=str(har_path), record_har_content="embed"
                )
                context.set_default_timeout(_ACTION_TIMEOUT_MS)
                context.set_default_navigation_timeout(_NAVIGATION_TIMEOUT_MS)
                context.route(
                    "**/*", _scope_router(allowed, skipped, allow_writes=card.target_is_sandbox)
                )
                context.route_web_socket(re.compile(".*"), _websocket_router(allowed, skipped))
                page = context.new_page()
                # A popup (window.open, target=_blank) would keep loading and polling the
                # target outside the crawl's pacing: close it; a link it opened is not followed.
                context.on("page", lambda popup: _close_popup(popup, page, skipped))
                if may_click:  # a clicked "delete" may ask confirm(); the sandbox says yes
                    page.on("dialog", lambda dialog: dialog.accept())
                pages = _crawl(
                    page, config, store, allowed, sleep, skipped, clicks, may_click=may_click
                )
                context.close()  # flushes the HAR to disk
            finally:
                browser.close()
        har = json.loads(har_path.read_text(encoding="utf-8"))

    har_ref = store.put_json(Zone.DIRTY, "har", config.start_url, har)
    parsed = parse_har(har, card.allowed_domains)
    expression_refs: list[str] = []
    for asset in parsed.expression:
        ref = store.put(
            Zone.DIRTY, "expression", asset.url, asset.content.encode("utf-8"), {"url": asset.url}
        )
        if ref.id not in expression_refs:
            expression_refs.append(ref.id)
    for asset in parsed.documents:
        store.put(
            Zone.DIRTY, "document", asset.url, asset.content.encode("utf-8"), {"url": asset.url}
        )

    store.ledger.append(
        "observe.explore",
        Zone.DIRTY.value,
        _ACTOR,
        {
            "pages": len(pages),
            "har_ref": har_ref.id,
            "expressions": len(expression_refs),
            "dropped_assets": len(parsed.dropped_assets),
            "skipped": skipped,
            "clicks": len(clicks),
            "destructive_clicks": [
                c.model_dump(mode="json") for c in clicks if c.destructive
            ],
        },
    )
    return ExplorationResult(
        pages=pages,
        har_ref=har_ref.id,
        expression_refs=expression_refs,
        skipped=skipped,
        clicks=clicks,
    )
