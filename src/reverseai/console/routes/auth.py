"""Token login for a console bound to a non-loopback address.

The token is sent in a POST form, never in the URL: a URL lands in the browser history and in
access logs (whose query strings the CLI's server drops anyway, see `RedactQueryFilter`).
"""

from __future__ import annotations

from fastapi import APIRouter, Form
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from reverseai.console.routes import console, require_csrf
from reverseai.console.security import SESSION_COOKIE, session_value, token_matches
from reverseai.console.templating import render

router = APIRouter()

_TITLE = "Нужен токен доступа"
_MESSAGE = (
    "Консоль доступна не только с этой машины. Введите токен доступа или передайте заголовок "
    "Authorization: Bearer."
)


def login_page(request: Request, status_code: int, error: str | None = None) -> Response:
    return render(request, "login.html", status_code, title=_TITLE, message=_MESSAGE,
                  status=status_code if status_code != 200 else None, error=error)


def unauthorized(request: Request) -> Response:
    return login_page(request, 401)


@router.get("/login")
def login_form(request: Request) -> Response:
    if console(request).token is None:
        return RedirectResponse("/", status_code=303)
    return login_page(request, 200)


@router.post("/login")
def login(request: Request, csrf: str = Form(""), token: str = Form("")) -> Response:
    expected = console(request).token
    if expected is None:
        return RedirectResponse("/", status_code=303)
    require_csrf(request, csrf)
    if not token_matches(token, expected):
        return login_page(request, 401, "Неверный токен доступа.")
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(SESSION_COOKIE, session_value(expected), httponly=True,
                        samesite="strict", path="/")
    return response
