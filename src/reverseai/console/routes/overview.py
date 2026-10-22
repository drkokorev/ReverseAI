"""Project overview page: timeline, KPIs, zones, ledger, phase controls and the job panel."""

from __future__ import annotations

from fastapi import APIRouter, Query
from starlette.requests import Request
from starlette.responses import Response

from reverseai.console.read.overview import LEDGER_LIMIT, overview
from reverseai.console.read.projects import MODE_LABELS, target_host
from reverseai.console.routes import console
from reverseai.console.templating import render

router = APIRouter()


def render_overview(
    request: Request,
    name: str,
    *,
    error: str | None = None,
    status_code: int = 200,
    type_prefix: str = "",
    show_all: bool = False,
    show_artifacts: bool = False,
) -> Response:
    ctx = console(request)
    project = ctx.projects.get(name)
    view = overview(ctx.artifacts, project, type_prefix, None if show_all else LEDGER_LIMIT,
                    show_artifacts)
    job = ctx.jobs.current(name)
    return render(
        request,
        "project.html",
        status_code,
        active="overview",
        project_name=name,
        card=project.card,
        mode=MODE_LABELS[project.card.mode],
        host=target_host(project),
        view=view,
        job=job,
        busy=job is not None and job.running,
        error=error,
        type_prefix=type_prefix,
    )


@router.get("/projects/{name}")
def project_page(
    request: Request,
    name: str,
    type_prefix: str = Query("", alias="type"),
    show_all: str = Query("", alias="all"),
    show_artifacts: str = Query("", alias="artifacts"),
) -> Response:
    return render_overview(request, name, type_prefix=type_prefix.strip(),
                           show_all=bool(show_all), show_artifacts=bool(show_artifacts))
