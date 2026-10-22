"""HTTP routes of the console, one module per page or action group."""

from __future__ import annotations

from starlette.requests import Request

from reverseai.console.context import ConsoleContext
from reverseai.console.security import csrf_matches


class CsrfRejected(PermissionError):
    """A POST without the page's CSRF token."""


def console(request: Request) -> ConsoleContext:
    return request.app.state.console


def require_csrf(request: Request, token: str) -> None:
    if not csrf_matches(token, console(request).csrf_token):
        raise CsrfRejected()
