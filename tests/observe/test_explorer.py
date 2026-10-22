import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from reverseai.bench.server import load_target, serve_asgi
from reverseai.observe.explorer import ExplorerConfig, explore
from reverseai.observe.har import parse_har
from reverseai.project import Attestation, IntakeError, Mode, ProjectCard
from reverseai.provenance.ledger import Ledger
from reverseai.zones.store import ArtifactStore, Zone

taskboard = load_target("taskboard")


def chromium_missing() -> str | None:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            if Path(p.chromium.executable_path).exists():
                return None
    except Exception as exc:  # noqa: BLE001 - any failure means "cannot run browser tests"
        return f"playwright unavailable: {exc}"
    return "Playwright Chromium is not installed (run `uv run playwright install chromium`)"


needs_browser = pytest.mark.skipif(
    chromium_missing() is not None, reason=chromium_missing() or ""
)


def make_card(base_url: str, *, sandbox: bool) -> ProjectCard:
    return ProjectCard(
        name="Demo",
        mode=Mode.LEGACY,
        target_base_url=base_url,
        allowed_domains=[urlparse(base_url).hostname or ""],
        target_is_sandbox=sandbox,
        attestation=Attestation(
            lawful_access=True, basis="own", signed_by="t", signed_at="2026-10-20T10:00:00Z"
        ),
        product_name="Acme Board",
    )


@pytest.fixture
def store(tmp_path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts", Ledger(tmp_path / "ledger.jsonl"))


@pytest.fixture
def project_on_taskboard(store):
    app = taskboard.create_app()
    with serve_asgi(app) as url:
        card = make_card(url, sandbox=True)
        cfg = ExplorerConfig(
            start_url=url + "/",
            allowed_domains=card.allowed_domains,
            max_pages=5,
            delay_s=0,
            submit_forms=True,
        )
        yield cfg, card, store


@pytest.mark.browser
@needs_browser
def test_explore_taskboard_records_api_and_expression(project_on_taskboard):
    cfg, card, store = project_on_taskboard
    res = explore(cfg, card, store)
    page = next(p for p in res.pages if p.title == "TaskBoard Pro")
    assert page.text_excerpt and len(page.text_excerpt) <= 2000
    (form,) = page.forms
    assert form.method == "POST"
    assert {(f.name, f.type, f.required) for f in form.fields} == {
        ("title", "text", True),
        ("priority", "select", False),
    }
    assert "Add task" in page.buttons

    har = parse_har(store.get_json(res.har_ref, Zone.VERIFIER), card.allowed_domains)
    assert any(e.method == "POST" and e.path == "/api/tasks" for e in har.exchanges)
    posted = next(e for e in har.exchanges if e.method == "POST" and e.path == "/api/tasks")
    assert posted.status == 201 and posted.request_json["title"].startswith("Sample ")

    assert res.expression_refs
    assert all(store.ref(r).zone == Zone.DIRTY for r in res.expression_refs)
    assert any(store.ref(r).name.endswith("/static/app.js") for r in res.expression_refs)
    assert all(store.ref(r).kind == "expression" for r in res.expression_refs)
    assert store.ref(res.expression_refs[0]).meta["url"].startswith(cfg.start_url[:-1])
    assert [r.kind for r in store.list(Zone.DIRTY, "document")]
    assert store.ref(res.har_ref).kind == "har"

    shot = store.ref(page.screenshot_ref)
    assert (shot.kind, shot.zone) == ("screenshot", Zone.DIRTY)
    assert store.get(shot.id, Zone.DIRTY).startswith(b"\x89PNG")
    assert store.list(Zone.DIRTY, "page")

    (event,) = [e for e in store.ledger.events() if e.type == "observe.explore"]
    assert (event.zone, event.actor) == ("dirty", "observer")
    assert event.payload["pages"] == len(res.pages)
    assert event.payload["har_ref"] == res.har_ref
    assert event.payload["expressions"] == len(res.expression_refs)


@pytest.mark.browser
@needs_browser
def test_explore_without_submit_does_not_write(project_on_taskboard):
    cfg, card, store = project_on_taskboard
    cfg = cfg.model_copy(update={"submit_forms": False})
    res = explore(cfg, card, store)
    har = parse_har(store.get_json(res.har_ref, Zone.VERIFIER), card.allowed_domains)
    assert not any(e.method == "POST" for e in har.exchanges)
    assert any(e.method == "GET" and e.path == "/api/tasks" for e in har.exchanges)


@pytest.mark.browser
@needs_browser
def test_explore_follows_only_in_domain_links_and_respects_max_pages(store):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI()
    hits: list[str] = []

    def page(path: str, links: list[str]) -> None:
        body = "<html><head><title>{}</title></head><body>{}</body></html>".format(
            path, "".join(f'<a href="{href}">x</a>' for href in links)
        )

        @app.get(path, response_class=HTMLResponse)
        def _handler(body=body, path=path) -> str:
            hits.append(path)
            return body

    page("/", ["/a#frag", "/a", "/b", "https://other.example.org/z", "/logo.png", "/x.js",
               "mailto:a@b.c"])
    page("/a", ["/", "/c"])
    page("/b", [])
    page("/c", [])

    with serve_asgi(app) as url:
        card = make_card(url, sandbox=False)
        cfg = ExplorerConfig(
            start_url=url + "/", allowed_domains=card.allowed_domains, max_pages=3, delay_s=0
        )
        res = explore(cfg, card, store)
    assert [urlparse(p.url).path for p in res.pages] == ["/", "/a", "/b"]
    assert hits.count("/a") == 1  # fragment and duplicate collapsed
    assert "/c" not in hits
    root = res.pages[0]
    assert sorted(urlparse(u).path for u in root.links) == ["/a", "/b"]


@pytest.mark.browser
@needs_browser
def test_explore_sleeps_between_navigations(store):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return '<title>r</title><a href="/a">a</a>'

    @app.get("/a", response_class=HTMLResponse)
    def _a() -> str:
        return "<title>a</title>"

    sleeps: list[float] = []
    with serve_asgi(app) as url:
        card = make_card(url, sandbox=False)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=card.allowed_domains, delay_s=0.5)
        explore(cfg, card, store, sleep=sleeps.append)
    assert sleeps == [0.5]


@pytest.mark.browser
@needs_browser
def test_explore_never_contacts_out_of_scope_hosts(store):
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse

    foreign_hits: list[str] = []
    foreign = FastAPI()

    @foreign.api_route("/{rest:path}", methods=["GET", "POST"])
    async def _record(rest: str, request: Request) -> HTMLResponse:
        foreign_hits.append(f"{request.method} /{rest}")
        return HTMLResponse("<title>foreign</title>")

    with serve_asgi(foreign) as foreign_url:
        foreign_port = urlparse(foreign_url).port
        # same machine, different host name: not in allowed_domains
        out_of_scope = f"http://localhost:{foreign_port}"
        foreign_hits.clear()  # drop serve_asgi's readiness probe
        local = FastAPI()

        @local.get("/", response_class=HTMLResponse)
        def _root() -> str:
            return (
                "<title>local</title>"
                f'<img src="{out_of_scope}/pixel.png">'
                f'<form action="{out_of_scope}/x" method="post">'
                '<input type="text" name="q"><button type="submit">Go</button></form>'
                '<form action="/in" method="post">'
                '<input type="text" name="n"><button type="submit">Ok</button></form>'
            )

        @local.post("/in", response_class=HTMLResponse)
        def _in() -> str:
            return "<title>in</title>"

        with serve_asgi(local) as url:
            card = make_card(url, sandbox=True)
            cfg = ExplorerConfig(
                start_url=url + "/",
                allowed_domains=["127.0.0.1"],
                delay_s=0,
                submit_forms=True,
            )
            res = explore(cfg, card, store)

    assert foreign_hits == []
    assert f"{out_of_scope}/x" in res.skipped
    assert f"{out_of_scope}/pixel.png" in res.skipped
    (event,) = [e for e in store.ledger.events() if e.type == "observe.explore"]
    assert event.payload["skipped"] == res.skipped
    entries = store.get_json(res.har_ref, Zone.VERIFIER)["log"]["entries"]
    # the in-scope form still ran (an HTML response, so it is not a parsed API exchange)
    assert any(
        e["request"]["method"] == "POST" and e["request"]["url"].endswith("/in") for e in entries
    )


@pytest.mark.browser
@needs_browser
def test_explore_records_skipped_pages_and_survives_long_polling(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, PlainTextResponse

    from reverseai.observe import explorer as explorer_module

    monkeypatch.setattr(explorer_module, "_SETTLE_TIMEOUT_S", 1.0)
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return '<title>r</title><a href="/text">t</a><a href="/slow">s</a>'

    @app.get("/text", response_class=PlainTextResponse)
    def _text() -> str:
        return "not html"

    @app.get("/slow", response_class=HTMLResponse)
    async def _slow() -> str:
        return (
            "<title>slow</title><script>"
            "fetch('/hang').catch(function(){});</script>"
        )

    import asyncio

    @app.get("/hang")
    async def _hang() -> PlainTextResponse:
        await asyncio.sleep(4)
        return PlainTextResponse("late")

    with serve_asgi(app) as url:
        card = make_card(url, sandbox=False)
        cfg = ExplorerConfig(
            start_url=url + "/", allowed_domains=card.allowed_domains, delay_s=0
        )
        res = explore(cfg, card, store)
    assert [p.title for p in res.pages] == ["r", "slow"]  # long-polling page is still observed
    assert res.skipped == [url + "/text"]


def test_submit_forms_requires_sandbox(store):
    card = make_card("http://127.0.0.1:1", sandbox=False)
    cfg = ExplorerConfig(
        start_url="http://127.0.0.1:1/", allowed_domains=card.allowed_domains, submit_forms=True
    )
    with pytest.raises(IntakeError):
        explore(cfg, card, store)
    assert store.list() == []


def test_start_url_must_be_in_allowed_domains(store):
    card = make_card("http://127.0.0.1:1", sandbox=True)
    cfg = ExplorerConfig(start_url="http://evil.example.org/", allowed_domains=card.allowed_domains)
    with pytest.raises(IntakeError):
        explore(cfg, card, store)


def test_config_domains_cannot_widen_the_card_scope(store):
    card = make_card("http://127.0.0.1:1", sandbox=True)
    cfg = ExplorerConfig(
        start_url="http://127.0.0.1:1/", allowed_domains=["127.0.0.1", "evil.example.org"]
    )
    with pytest.raises(IntakeError):
        explore(cfg, card, store)


def test_config_defaults():
    cfg = ExplorerConfig(start_url="http://x/", allowed_domains=["x"])
    assert (cfg.max_pages, cfg.delay_s, cfg.submit_forms, cfg.max_clicks) == (50, 0.5, False, 50)
    assert json.loads(cfg.model_dump_json())["start_url"] == "http://x/"


# --- final review fixes --------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, method: str, url: str):
        self.method = method
        self.url = url


class _FakeRoute:
    def __init__(self, method: str, url: str):
        self.request = _FakeRequest(method, url)
        self.outcome = ""

    def continue_(self) -> None:
        self.outcome = "continue"

    def abort(self) -> None:
        self.outcome = "abort"


@pytest.mark.parametrize(
    ("sandbox", "method", "outcome"),
    [(False, "GET", "continue"), (False, "HEAD", "continue"), (False, "POST", "abort"),
     (False, "DELETE", "abort"), (True, "POST", "continue")],
)
def test_router_aborts_writes_to_a_non_sandbox_target(sandbox, method, outcome):
    from reverseai.observe.explorer import _scope_router

    skipped: list[str] = []
    route = _FakeRoute(method, "http://127.0.0.1:8000/api/tasks")
    _scope_router({"127.0.0.1"}, skipped, allow_writes=sandbox)(route)
    assert route.outcome == outcome
    assert skipped == ([f"{method} http://127.0.0.1:8000/api/tasks"] if outcome == "abort" else [])


@pytest.mark.browser
@needs_browser
def test_explore_never_writes_to_a_non_sandbox_target(store):
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse

    writes: list[str] = []
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return "<title>t</title><script>fetch('/api/hit', {method: 'POST'})</script>"

    @app.api_route("/api/hit", methods=["POST"])
    async def _hit(request: Request) -> dict:
        writes.append(request.method)
        return {}

    with serve_asgi(app) as url:
        card = make_card(url, sandbox=False)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=["127.0.0.1"], delay_s=0)
        res = explore(cfg, card, store)
    assert writes == []
    assert f"POST {url}/api/hit" in res.skipped


# --- clicks on non-form controls ------------------------------------------------------------


@pytest.mark.browser
@needs_browser
def test_explore_taskboard_clicks_toggle_and_delete(project_on_taskboard):
    cfg, card, store = project_on_taskboard
    res = explore(cfg, card, store)
    har = parse_har(store.get_json(res.har_ref, Zone.VERIFIER), card.allowed_domains)
    methods = {(e.method, e.path.rsplit("/", 1)[0]) for e in har.exchanges if 200 <= e.status < 300}
    assert ("PATCH", "/api/tasks") in methods
    assert ("DELETE", "/api/tasks") in methods
    assert any(c.destructive for c in res.clicks)
    (event,) = [e for e in store.ledger.events() if e.type == "observe.explore"]
    assert event.payload["clicks"] == len(res.clicks)
    assert event.payload["destructive_clicks"] == [
        c.model_dump(mode="json") for c in res.clicks if c.destructive
    ]


def _controls_app(hits: list[str]):
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return """<title>c</title>
<ul id="rows"></ul>
<button id="b1" onclick="fetch('/api/hit/refresh', {method: 'POST'})">Refresh</button>
<div role="button" onclick="fetch('/api/hit/star', {method: 'PUT'})">Star</div>
<input type="checkbox" onchange="fetch('/api/hit/flag', {method: 'PATCH'})">
<button style="display:none" onclick="fetch('/api/hit/hidden', {method: 'POST'})">Hidden</button>
<button disabled onclick="fetch('/api/hit/disabled', {method: 'POST'})">Off</button>
<form onsubmit="event.preventDefault()"><input name="q">
  <button type="button" onclick="fetch('/api/hit/inform', {method: 'POST'})">In form</button>
</form>
<script>
function draw() {
  const rows = document.getElementById('rows');
  rows.replaceChildren();
  for (const id of [1, 2, 3]) {
    const b = document.createElement('button');
    b.textContent = 'Delete';
    b.onclick = () => fetch('/api/hit/delete-' + id, {method: 'DELETE'}).then(draw);
    rows.append(b);
  }
}
draw();
</script>"""

    @app.api_route("/api/hit/{name}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def _hit(name: str, request: Request) -> dict:
        hits.append(f"{request.method} {name}")
        return {}

    return app


@pytest.mark.browser
@needs_browser
def test_explore_clicks_each_distinct_control_once_on_a_sandbox(store):
    hits: list[str] = []
    sleeps: list[float] = []
    with serve_asgi(_controls_app(hits)) as url:
        card = make_card(url, sandbox=True)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=card.allowed_domains, delay_s=0.25)
        res = explore(cfg, card, store, sleep=sleeps.append)
    # one of the three identical "Delete" rows; nothing hidden, disabled or inside a form
    assert sorted(hits) == ["DELETE delete-1", "PATCH flag", "POST refresh", "PUT star"]
    assert len(res.clicks) == 4 and sleeps == [0.25] * 4
    assert [c.control for c in res.clicks if c.destructive] == ["button 'Delete'"]
    (event,) = [e for e in store.ledger.events() if e.type == "observe.explore"]
    assert event.payload["clicks"] == 4
    assert event.payload["destructive_clicks"] == [
        {"page": url + "/", "control": "button 'Delete'", "destructive": True}
    ]


@pytest.mark.browser
@needs_browser
def test_explore_respects_max_clicks(store):
    hits: list[str] = []
    with serve_asgi(_controls_app(hits)) as url:
        card = make_card(url, sandbox=True)
        cfg = ExplorerConfig(
            start_url=url + "/", allowed_domains=card.allowed_domains, delay_s=0, max_clicks=2
        )
        res = explore(cfg, card, store)
    assert len(hits) == len(res.clicks) == 2


@pytest.mark.browser
@needs_browser
def test_explore_never_clicks_a_non_sandbox_target(store):
    hits: list[str] = []
    with serve_asgi(_controls_app(hits)) as url:
        card = make_card(url, sandbox=False)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=card.allowed_domains, delay_s=0)
        res = explore(cfg, card, store)
    assert hits == [] and res.clicks == []
    (event,) = [e for e in store.ledger.events() if e.type == "observe.explore"]
    assert (event.payload["clicks"], event.payload["destructive_clicks"]) == (0, [])


@pytest.mark.browser
@needs_browser
def test_explore_follows_a_click_that_navigates(store):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return "<title>r</title><button onclick=\"location.href='/next'\">Next</button>"

    @app.get("/next", response_class=HTMLResponse)
    def _next() -> str:
        return "<title>n</title>"

    with serve_asgi(app) as url:
        card = make_card(url, sandbox=True)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=card.allowed_domains, delay_s=0)
        res = explore(cfg, card, store)
    assert [p.title for p in res.pages] == ["r", "n"]
    assert [c.control for c in res.clicks] == ["button 'Next'"]


@pytest.mark.parametrize(
    ("label", "destructive"),
    [("Delete", True), ("x", True), ("×", True), ("Log out", True), ("Удалить", True),
     ("Clear all", True), ("Dropdown", False), ("Save", False), ("Next", False), ("Index", False)],
)
def test_destructive_labels(label, destructive):
    from reverseai.observe.explorer import _DESTRUCTIVE_RE

    assert bool(_DESTRUCTIVE_RE.search(label)) is destructive


# --- audit 2026-10-22 ------------------------------------------------------------------------


@pytest.mark.browser
@needs_browser
def test_explore_blocks_out_of_scope_websockets(store):
    import socket
    import threading

    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    connections: list[bytes] = []
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.2)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def accept() -> None:
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            with conn:
                conn.settimeout(1.0)
                try:
                    connections.append(conn.recv(1024))
                except OSError:
                    connections.append(b"")

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    foreign = f"ws://localhost:{port}/socket"
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return f"<title>w</title><script>new WebSocket({foreign!r});</script>"

    try:
        with serve_asgi(app) as url:
            card = make_card(url, sandbox=True)
            cfg = ExplorerConfig(start_url=url + "/", allowed_domains=["127.0.0.1"], delay_s=0)
            res = explore(cfg, card, store)
    finally:
        stop.set()
        thread.join(timeout=2)
        listener.close()
    assert connections == []
    assert foreign in res.skipped


@pytest.mark.browser
@needs_browser
def test_explore_sleeps_before_returning_to_a_page_a_click_left(store):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return "<title>r</title><button onclick=\"location.href='/next'\">Next</button>"

    @app.get("/next", response_class=HTMLResponse)
    def _next() -> str:
        return "<title>n</title>"

    sleeps: list[float] = []
    with serve_asgi(app) as url:
        card = make_card(url, sandbox=True)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=card.allowed_domains,
                             delay_s=0.25)
        res = explore(cfg, card, store, sleep=sleeps.append)
    assert [p.title for p in res.pages] == ["r", "n"]
    # click, return to "/", crawl "/next": every request toward the target is paced
    assert sleeps == [0.25, 0.25, 0.25]


@pytest.mark.browser
@needs_browser
def test_explore_sleeps_before_returning_to_a_page_a_form_left(store):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return (
            '<title>r</title><form action="/in" method="post">'
            '<input type="text" name="n"><button type="submit">Ok</button></form>'
        )

    @app.post("/in", response_class=HTMLResponse)
    def _in() -> str:
        return "<title>in</title>"

    sleeps: list[float] = []
    with serve_asgi(app) as url:
        card = make_card(url, sandbox=True)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=card.allowed_domains,
                             delay_s=0.25, submit_forms=True, max_clicks=0)
        explore(cfg, card, store, sleep=sleeps.append)
    assert sleeps == [0.25, 0.25]  # before the submit, before going back to "/"


@pytest.mark.browser
@needs_browser
def test_explore_closes_popups_a_click_opens(store):
    import asyncio

    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    hits: list[str] = []
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return (
            "<title>r</title><a href=\"/slow\">s</a>"
            "<button onclick=\"window.open('/popup')\">Open</button>"
        )

    @app.get("/popup", response_class=HTMLResponse)
    def _popup() -> str:
        return "<title>p</title><script>setTimeout(() => fetch('/late'), 1000)</script>"

    @app.get("/late")
    def _late() -> dict:
        hits.append("late")
        return {}

    @app.get("/slow", response_class=HTMLResponse)
    def _slow() -> str:
        return "<title>s</title><script>fetch('/hang')</script>"

    @app.get("/hang")
    async def _hang() -> dict:
        await asyncio.sleep(2)
        return {}

    with serve_asgi(app) as url:
        card = make_card(url, sandbox=True)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=card.allowed_domains,
                             delay_s=0)
        res = explore(cfg, card, store)
    assert [p.title for p in res.pages] == ["r", "s"]
    assert hits == []  # the popup was closed before its timer fired
    assert any(entry.startswith("popup ") for entry in res.skipped)


@pytest.mark.browser
@needs_browser
def test_explore_skips_a_page_it_cannot_read_and_goes_on(store, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from playwright.sync_api import Error as PlaywrightError

    from reverseai.observe import explorer as explorer_module

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def _root() -> str:
        return '<title>r</title><a href="/gone">g</a><a href="/b">b</a>'

    @app.get("/gone", response_class=HTMLResponse)
    def _gone() -> str:
        return "<title>gone</title>"

    @app.get("/b", response_class=HTMLResponse)
    def _b() -> str:
        return "<title>b</title>"

    real = explorer_module._observe

    def flaky(page, shot, allowed):
        if page.url.endswith("/gone"):
            raise PlaywrightError("Execution context was destroyed")
        return real(page, shot, allowed)

    monkeypatch.setattr(explorer_module, "_observe", flaky)
    with serve_asgi(app) as url:
        card = make_card(url, sandbox=False)
        cfg = ExplorerConfig(start_url=url + "/", allowed_domains=card.allowed_domains,
                             delay_s=0)
        res = explore(cfg, card, store)
    assert [p.title for p in res.pages] == ["r", "b"]
    assert url + "/gone" in res.skipped
