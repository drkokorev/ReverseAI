"""The console in English (the default) and the EN/RU switch: cookie, `<html lang>`, jobs."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from reverseai.console import create_app

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
URL = "/projects/console-demo"


def _visible(html: str) -> str:
    """Page text without the language switch (its RU option is labelled in Latin anyway)."""
    return re.sub(r"<[^>]+>", " ", html)


def test_pages_are_english_by_default(console, approver_name) -> None:
    c = console("audited")
    pages = {
        "/": ["PROJECTS", "Every project moves through nine phases", "ALL PROJECTS · 1",
              "clone: Tasklet", "NEW PROJECT"],
        "/projects/new": ["NEW PROJECT", "PHASE 01 · INTAKE", "Clone product name",
                          "DATA POLICY", "Self-hosted", "CREATE PROJECT"],
        URL: ["PROJECT Console Demo", "9 of 9 phases complete; the provenance ledger is intact.",
              "TIMELINE", "PROVENANCE LEDGER", "chain intact", "Sees the original",
              "RUN PHASES", "BUILD AND PARITY", "Rerunning a phase resets every later phase."],
        f"{URL}/release": ["PACKAGE v1", "PHASE 06 · BARRIER", "PACKAGE SIGNATURE",
                           "Package SHA-256 (spec + scenarios)", "RELEASED", "platform operator"],
        f"{URL}/release?tab=cleanup": ["SANITIZER FINDINGS", "WITHHELD EXPECTED VALUES",
                                       "DROPPED BY ORACLE"],
        f"{URL}/parity": ["PARITY", "THRESHOLD", "CODE SIMILARITY", "EVIDENCE PACK", "DOWNLOAD",
                          "This document is not a legal opinion."],
        f"{URL}/costs": ["COSTS", "LLM CALLS", "BY ROLE", "BY MODEL", "MODEL (PROVIDER)"],
    }
    for url, needles in pages.items():
        r = c.get(url)
        assert r.status_code == 200, url
        assert '<html lang="en">' in r.text, url
        for needle in needles:
            assert needle in r.text, (url, needle)
        text = _visible(r.text).replace(approver_name, "")
        assert not CYRILLIC.search(text), (url, CYRILLIC.findall(text)[:5])


def test_overview_details_and_kpis_in_english(console) -> None:
    html = console("audited").get(URL).text
    assert re.search(r"1 page, \d+ exchanges, 2 API probes<", html)
    assert "Access attested; risks: none found" in html
    assert re.search(r">\d+ scenarios<", html)
    assert re.search(r">\d+ features, \d+ rules<", html)
    assert re.search(r">1 iteration, \d+ of \d+<", html)
    assert re.search(r"\d+ of \d+ scenarios?", html)
    assert re.search(r"\d\.\d{3} in 1 round<", html)
    assert re.search(r"\d+ calls?", html)


def test_error_pages_in_english(console) -> None:
    c = console("created")
    r = c.get("/projects/nope")
    assert r.status_code == 404
    assert "Project not found" in r.text and "ERROR · 404" in r.text
    assert "ALL PROJECTS" in r.text
    r = c.get("/no/such/page")
    assert r.status_code == 404 and "Page not found" in r.text
    r = c.client.post("/projects", data={"csrf": "forged"}, follow_redirects=False)
    assert r.status_code == 403
    assert "Form expired" in r.text and "Reload the page and try again." in r.text
    r = c.post(f"{URL}/run/nope")
    assert r.status_code == 404 and "No such phase: “nope”." in r.text


def test_forms_report_errors_in_english(console) -> None:
    c = console("created")
    r = c.post("/projects", {"name": ""})
    assert r.status_code == 400 and "Enter a project name." in r.text
    r = c.post("/projects", {"name": "Other", "target_base_url": "https://evil.example/",
                             "allowed_domains": "app.example.com", "product_name": "X",
                             "jurisdictions": "us", "lawful_access": "on"})
    assert r.status_code == 400
    assert "Target host “evil.example” is not among the allowed domains." in r.text
    r = c.post(f"{URL}/run/observe", {"max_pages": "0"})
    assert "Page count must be a whole number of 1 or more." in r.text


def test_release_approval_errors_in_english(console) -> None:
    c = console("prepared")
    url = f"{URL}/release/approve"
    assert "Enter who approves the package." in c.post(url, {"approver": " "}).text
    r = c.post(url, {"approver": "Anna", "role": "operator"})
    assert "Confirm that you reviewed the package: tick the checkbox." in r.text
    r = c.post(url, {"approver": "Anna", "role": "operator", "confirm": "on", "sha": "0" * 64})
    assert r.status_code == 409
    assert "Error: the draft has changed — reload the page and review the package again" in r.text


def test_login_page_in_english(console) -> None:
    c = console("created", token="s3cret-token")
    r = c.get("/")
    assert r.status_code == 401
    assert '<html lang="en">' in r.text
    assert "Access token required" in r.text and "SIGN IN" in r.text
    assert "Wrong access token." in c.post("/login", {"token": "wrong"}).text


def test_job_log_is_english(console) -> None:
    c = console("observed")
    c.post(f"{URL}/run/oracle")
    job = c.wait()
    assert job.status == "succeeded", job.message
    assert job.label == "Behavior oracle"
    assert job.status_label == "done"
    assert "Phase “Behavior oracle” (oracle) complete." in job.log


# --- the language switch -------------------------------------------------------------------


def test_switch_sets_a_cookie_and_returns_to_the_page(console) -> None:
    c = console("audited")
    r = c.get("/lang/ru", params={"next": f"{URL}/parity"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"{URL}/parity"
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("reverseai_lang=ru;") and "HttpOnly" in cookie
    assert "Path=/" in cookie and "SameSite=lax" in cookie
    html = c.get(f"{URL}/parity").text  # the client keeps the cookie
    assert '<html lang="ru">' in html and "ПАРИТЕТ" in html
    c.get("/lang/en", follow_redirects=False)
    assert '<html lang="en">' in c.get("/").text


def test_switch_links_mark_the_current_language_and_return_here(console) -> None:
    c = console("audited")
    html = c.get(f"{URL}?type=barrier.").text
    assert 'href="/lang/ru?next=/projects/console-demo%3Ftype%3Dbarrier." hreflang="ru"' in html
    assert re.search(r'hreflang="en" lang="en" aria-current="true">EN<', html)
    assert not re.search(r'hreflang="ru" lang="ru" aria-current', html)


@pytest.mark.parametrize("target", ["https://evil.example/", "//evil.example/", "/\\evil",
                                    "javascript:alert(1)", ""])
def test_switch_never_redirects_off_the_console(console, target) -> None:
    r = console("created").get("/lang/ru", params={"next": target}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_unknown_language_is_404(console) -> None:
    c = console("created")
    r = c.get("/lang/de", follow_redirects=False)
    assert r.status_code == 404 and "set-cookie" not in r.headers
    assert c.get("/lang/RU", follow_redirects=False).status_code == 404
    c.client.cookies.set("reverseai_lang", "de")  # an unknown cookie value: the default
    assert '<html lang="en">' in c.get("/").text


def test_console_default_language_option(stage_root) -> None:
    root = stage_root("created")
    html = TestClient(create_app(root, lang="ru")).get("/").text
    assert '<html lang="ru">' in html and "ВСЕ ПРОЕКТЫ" in html
    client = TestClient(create_app(root, lang="ru"))
    client.get("/lang/en")
    assert '<html lang="en">' in client.get("/").text  # the viewer's choice wins
    with pytest.raises(ValueError, match="unsupported console language"):
        create_app(root, lang="de")


def test_switch_works_on_the_login_page(console) -> None:
    c = console("created", token="s3cret-token")
    r = c.get("/lang/ru", params={"next": "/login"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    r = c.get("/")
    assert r.status_code == 401 and "Нужен токен доступа" in r.text
    assert c.get("/lang/../projects/console-demo").status_code == 401


def test_a_form_answer_switches_back_to_the_project(console) -> None:
    c = console("created")
    html = c.post(f"{URL}/run/observe", {"max_pages": "0"}).text
    assert f'href="/lang/ru?next={URL}"' in html


def test_job_runs_in_the_language_of_the_request(console) -> None:
    c = console("observed")
    c.client.cookies.set("reverseai_lang", "ru")
    c.post(f"{URL}/run/oracle")
    job = c.wait()
    assert job.label == "Оракул поведения"
    assert "Этап «Оракул поведения» (oracle) завершён." in job.log
    c.client.cookies.set("reverseai_lang", "en")
    assert c.get(f"{URL}/job").json()["job"]["status_label"] == "done"


def test_cli_console_lang_sets_the_default(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from reverseai import cli

    calls: list = []
    monkeypatch.setattr(cli, "_serve", lambda app, host, port: calls.append(app))
    monkeypatch.delenv("REVERSEAI_CONSOLE_TOKEN", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli.app, ["console", "--projects-root", str(tmp_path)])
    assert "ReverseAI console: http://127.0.0.1:8765" in result.output
    result = runner.invoke(cli.app, ["console", "--projects-root", str(tmp_path),
                                     "--lang", "ru"])
    assert "Консоль ReverseAI: http://127.0.0.1:8765" in result.output
    result = runner.invoke(cli.app, ["--lang", "ru", "console", "--projects-root",
                                     str(tmp_path)])
    english, russian, global_ru = (
        TestClient(app, base_url="http://127.0.0.1").get("/").text for app in calls
    )
    assert '<html lang="en">' in english
    assert '<html lang="ru">' in russian and '<html lang="ru">' in global_ru
    result = runner.invoke(cli.app, ["console", "--projects-root", str(tmp_path),
                                     "--lang", "de"])
    assert result.exit_code == 2
