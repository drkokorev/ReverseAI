"""The EN/RU switch in the header: a cookie with the chosen language, then back to the page.

A plain link (GET), so it works without scripts and on the login page; it changes nothing but
the viewer's own display preference. `next` must be a path on this console (no open redirect).
"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from reverseai.console.security import LANG_COOKIE
from reverseai.console.templating import render_error
from reverseai.i18n import normalize, t

router = APIRouter()

_ONE_YEAR = 365 * 24 * 3600


def local_path(target: str) -> str:
    """`target` if it is a path on this site, else `/`."""
    if (
        not target.startswith("/")
        or target.startswith("//")
        or "\\" in target
        or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in target)
    ):
        return "/"
    return target


@router.get("/lang/{code}")
def switch_language(request: Request, code: str, next: str = "/") -> Response:
    lang = normalize(code)
    if lang is None or lang != code:
        return render_error(request, 404, t("errors.not_found.title"),
                            t("errors.not_found.message"))
    response = RedirectResponse(local_path(next), status_code=303)
    response.set_cookie(LANG_COOKIE, lang, max_age=_ONE_YEAR, httponly=True, samesite="lax",
                        path="/")
    return response
