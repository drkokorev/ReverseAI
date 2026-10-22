"""Security of the console: headers, CSRF, escaping, token and host checks."""

import pytest

from reverseai.console.security import is_loopback
from reverseai.pipeline import load_state, save_state
from reverseai.project import Attestation, Mode, ProjectCard, create_project

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


@pytest.fixture
def console_lang() -> str:
    return "ru"


PAGES = ["/", "/projects/new", "/projects/console-demo", "/projects/console-demo/release",
         "/projects/console-demo/parity", "/projects/console-demo/costs"]


def test_every_page_sends_security_headers(console) -> None:
    c = console("audited")
    for url in PAGES:
        r = c.get(url)
        assert r.status_code == 200, url
        csp = r.headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
        assert "https://fonts.googleapis.com" in csp and "https://fonts.gstatic.com" in csp
        assert "frame-ancestors 'none'" in csp
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "<script>" not in r.text  # no inline scripts
        assert 'src="/static/console.js"' in r.text


def test_static_assets_are_served(console) -> None:
    c = console("created")
    css = c.get("/static/console.css")
    assert css.status_code == 200 and "--bg" in css.text
    js = c.get("/static/console.js")
    assert js.status_code == 200 and "localStorage" in js.text


@pytest.mark.parametrize(
    ("url", "data"),
    [
        ("/projects", {"name": "x"}),
        ("/projects/console-demo/run/oracle", {}),
        ("/projects/console-demo/release/approve", {"approver": "A", "role": "operator"}),
    ],
)
def test_post_without_csrf_token_is_refused(console, url, data) -> None:
    c = console("prepared")
    before = len(c.project().ledger.events())
    r = c.client.post(url, data={**data, "csrf": "forged"}, follow_redirects=False)
    assert r.status_code == 403
    assert "Обновите страницу" in r.text
    r = c.client.post(url, data=data, follow_redirects=False)
    assert r.status_code == 403
    assert c.ctx.jobs.current("console-demo") is None
    assert len(c.project().ledger.events()) == before


def test_forms_carry_the_csrf_token(console) -> None:
    c = console("prepared")
    assert f'name="csrf" value="{c.csrf}"' in c.get("/projects/new").text
    assert f'name="csrf" value="{c.csrf}"' in c.get("/projects/console-demo").text
    assert f'name="csrf" value="{c.csrf}"' in c.get("/projects/console-demo/release").text


def test_untrusted_text_is_escaped(console) -> None:
    c = console("created")
    card = ProjectCard(
        name="<script>alert(1)</script> Demo", mode=Mode.LEGACY,
        target_base_url="https://app.example.com/", allowed_domains=["app.example.com"],
        attestation=Attestation(lawful_access=True, basis="<img src=x onerror=alert(2)>",
                                signed_by="I", signed_at="2026-10-22T00:00:00Z"),
        product_name="Tasklet <b>bold</b>",
    )
    project = create_project(card, c.root)
    save_state(project, load_state(project))
    listing = c.get("/").text
    page = c.get(f"/projects/{project.dir.name}").text
    for html in (listing, page):
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "<b>bold</b>" not in html


def test_unknown_project_is_404_in_russian(console) -> None:
    c = console("created")
    for url in ["/projects/nope", "/projects/nope/release", "/projects/..%2F..%2Fetc",
                "/projects/.workspaces"]:
        r = c.get(url)
        assert r.status_code == 404, url
        assert "не найден" in r.text  # «Проект не найден» or «Страница не найдена»
    assert "Проект не найден" in c.get("/projects/nope/parity").text


def test_token_is_required_when_configured(console) -> None:
    c = console("created", token="s3cret-token")
    r = c.get("/")
    assert r.status_code == 401
    assert "Нужен токен доступа" in r.text
    assert 'action="/login" method="post"' in r.text  # the 401 page is the login form
    assert c.get("/", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
    assert c.post("/login", {"token": "wrong"}).status_code == 401
    login = c.post("/login", {"token": "s3cret-token"})
    assert login.status_code == 303 and login.headers["location"] == "/"
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "s3cret-token" not in cookie  # the cookie holds a derived value, not the token
    assert c.get("/").status_code == 200  # the client kept the cookie
    assert "s3cret-token" not in c.get("/").text


def test_token_in_the_url_does_not_log_in(console) -> None:
    c = console("created", token="s3cret-token")
    r = c.get("/login", params={"token": "s3cret-token"}, follow_redirects=False)
    assert r.status_code == 200
    assert "set-cookie" not in r.headers
    assert 'name="token" type="password"' in r.text
    assert c.get("/").status_code == 401


def test_login_form_needs_the_csrf_token(console) -> None:
    c = console("created", token="s3cret-token")
    r = c.client.post("/login", data={"token": "s3cret-token"}, follow_redirects=False)
    assert r.status_code == 403
    assert "set-cookie" not in r.headers


def test_only_the_login_page_itself_is_public(console) -> None:
    c = console("created", token="s3cret-token")
    assert c.get("/loginx").status_code == 401
    assert c.get("/login/../projects/console-demo").status_code == 401


def test_access_log_drops_query_strings() -> None:
    import logging

    from reverseai.console.security import RedactQueryFilter

    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                               '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1:5000", "GET", "/login?token=s3cret", "1.1", 200),
                               None)
    assert RedactQueryFilter().filter(record) is True
    assert "s3cret" not in record.getMessage()
    assert "/login" in record.getMessage()


def test_host_header_is_checked_on_loopback(console) -> None:
    c = console("created", allowed_hosts=["127.0.0.1", "localhost"])
    assert c.get("/", headers={"host": "127.0.0.1:8765"}).status_code == 200
    assert c.get("/", headers={"host": "evil.example"}).status_code == 400


@pytest.mark.parametrize(
    ("host", "loopback"),
    [("127.0.0.1", True), ("localhost", True), ("::1", True), ("127.0.0.2", True),
     ("0.0.0.0", False), ("192.168.1.5", False), ("example.com", False), ("::", False)],
)
def test_is_loopback(host, loopback) -> None:
    assert is_loopback(host) is loopback


def test_non_ascii_session_cookie_is_refused_not_a_crash(console) -> None:
    from reverseai.console.security import SESSION_COOKIE

    c = console("created", token="s3cret-token")
    c.client.cookies.clear()
    r = c.get("/", headers={"cookie": f"{SESSION_COOKIE}=é".encode()})
    assert r.status_code == 401
    assert "Нужен токен доступа" in r.text
