"""Jinja environment (autoescape always on), display filters and the page renderer."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from starlette.requests import Request
from starlette.responses import Response

from reverseai.i18n import LANGS, get_language, t

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def parse_time(value: str | dt.datetime | None) -> dt.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        moment = value
    else:
        try:
            moment = dt.datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(dt.UTC)


def hms(value: str | dt.datetime | None) -> str:
    moment = parse_time(value)
    return moment.strftime("%H:%M:%S") if moment else "—"


def stamp(value: str | dt.datetime | None) -> str:
    moment = parse_time(value)
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC") if moment else "—"


def short(value: str | None, length: int = 10) -> str:
    return (value or "")[:length]


def project_path(name: str) -> str:
    """`/projects/<name>` with the directory name percent-encoded (spaces, `#`, `?`, Cyrillic)."""
    return "/projects/" + quote(name, safe="")


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,  # every template: target-originated text is untrusted
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(hms=hms, stamp=stamp, short=short, project_path=project_path)
    env.globals.update(t=t, langs=LANGS)
    return env


templates = Jinja2Templates(env=_environment())


def render(
    request: Request, template: str, status_code: int = 200, **context: Any
) -> Response:
    console = request.app.state.console
    context.setdefault("active", "")
    context.setdefault("project_name", None)
    name = context["project_name"]
    context.setdefault("project_url", project_path(name) if name is not None else None)
    return templates.TemplateResponse(
        request,
        template,
        {
            "csrf_token": console.csrf_token,
            "operator": console.operator,
            "operator_initials": console.operator_initials,
            "lang": get_language(),
            "here": _here(request, context["project_url"]),
            **context,
        },
        status_code=status_code,
    )


def _here(request: Request, project_url: str | None) -> str:
    """Where the language switch returns to: this page, or for a form answer (a POST) the
    project's overview or the projects list."""
    if request.method != "GET":
        return project_url or "/"
    path = request.url.path
    return f"{path}?{request.url.query}" if request.url.query else path


def render_error(request: Request, status_code: int, title: str, message: str) -> Response:
    return render(request, "error.html", status_code, title=title, message=message,
                  status=status_code)
