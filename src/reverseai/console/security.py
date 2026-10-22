"""Security of the console: loopback check, response headers, token login, CSRF.

- Bound to a loopback address the console needs no login; any other address requires
  `REVERSEAI_CONSOLE_TOKEN` (checked by the CLI before the server starts).
- With a token, every request except `/login` and `/static/` must carry it: as
  `Authorization: Bearer <token>`, or as the session cookie set by the login form (a POST to
  `/login`; the cookie holds an HMAC derived from the token, never the token itself).
- The access log of `reverseai console` drops query strings (`RedactQueryFilter`).
- Every POST carries the per-process CSRF token from the page's form.
- Content-Security-Policy: self only, plus Google Fonts; no inline scripts or styles.
- The display language comes from the `reverseai_lang` cookie (set by `/lang/en` or `/lang/ru`,
  public like `/login`), else the console's default (`LanguageMiddleware`).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from reverseai.i18n import LANGS, normalize, use_language

TOKEN_ENV = "REVERSEAI_CONSOLE_TOKEN"
SESSION_COOKIE = "reverseai_console"
LANG_COOKIE = "reverseai_lang"
LOOPBACK_HOSTS = ["127.0.0.1", "localhost", "::1", "[::1]"]

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}
_PUBLIC_PATHS = frozenset({"/login", *(f"/lang/{code}" for code in LANGS)})
_PUBLIC_PREFIXES = ("/static/",)

Handler = Callable[[Request], Awaitable[Response]]


def is_loopback(host: str) -> bool:
    if host.strip("[]").lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def session_value(token: str) -> str:
    """The cookie value for `token`: an HMAC, so the cookie never carries the token itself."""
    return hmac.new(token.encode("utf-8"), b"reverseai-console-session", hashlib.sha256).hexdigest()


def token_matches(given: str | None, token: str) -> bool:
    return given is not None and hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))


def csrf_matches(given: str | None, expected: str) -> bool:
    return bool(given) and hmac.compare_digest(str(given).encode("utf-8"), expected.encode("utf-8"))


def _authorized(request: Request, token: str) -> bool:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and token_matches(auth[7:].strip(), token):
        return True
    cookie = request.cookies.get(SESSION_COOKIE)
    # Bytes, not str: compare_digest raises TypeError on non-ASCII str (a forged cookie).
    return cookie is not None and hmac.compare_digest(
        cookie.encode("utf-8"), session_value(token).encode("utf-8")
    )


class RedactQueryFilter(logging.Filter):
    """Drops the query string from uvicorn access-log lines (no secrets in logs).

    uvicorn's access records carry `(client, method, path_with_query, http_version, status)`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (args[0], args[1], args[2].split("?", 1)[0], args[3], args[4])
        return True


class ErrorPageMiddleware(BaseHTTPMiddleware):
    """Turns an unhandled exception into the console's error page.

    Installed inside `SecurityHeadersMiddleware`, so the error page gets the same headers;
    Starlette's own server-error handler would answer with a bare page, outside every
    middleware.
    """

    def __init__(self, app, render: Callable[[Request, Exception], Response]) -> None:
        super().__init__(app)
        self._render = render

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001 - every failure becomes the console's page
            return self._render(request, exc)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Rejects requests without the token (only installed when a token is configured)."""

    def __init__(self, app, token: str, unauthorized: Callable[[Request], Response]) -> None:
        super().__init__(app)
        self._token = token
        self._unauthorized = unauthorized

    async def dispatch(self, request: Request, call_next: Handler) -> Response:
        path = request.url.path
        public = path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)
        if public or _authorized(request, self._token):
            return await call_next(request)
        return self._unauthorized(request)


class LanguageMiddleware:
    """Sets the active language for the request: the `reverseai_lang` cookie, else `default`.

    A plain ASGI middleware (outermost), so every page, error page, form message and the job
    started by the request see the same language.
    """

    def __init__(self, app: Any, default: str) -> None:
        self.app = app
        self.default = default

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        lang = normalize(Request(scope).cookies.get(LANG_COOKIE)) or self.default
        with use_language(lang):
            await self.app(scope, receive, send)
