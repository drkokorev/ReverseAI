"""Parity and evidence page, and the evidence pack download."""

from __future__ import annotations

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import FileResponse, Response

from reverseai.console.evidence import current_pack, outside_console
from reverseai.console.read.parity import parity_view
from reverseai.console.routes import console
from reverseai.console.templating import render, render_error
from reverseai.i18n import t
from reverseai.pipeline import Phase, load_state

router = APIRouter()


@router.get("/projects/{name}/parity")
def parity_page(request: Request, name: str) -> Response:
    ctx = console(request)
    project = ctx.projects.get(name)
    return render(request, "parity.html", active="parity", project_name=name,
                  card=project.card, view=parity_view(ctx.artifacts, project),
                  outside_message=outside_console())


@router.get("/projects/{name}/evidence.zip")
def evidence_download(request: Request, name: str) -> Response:
    ctx = console(request)
    project = ctx.projects.get(name)
    if Phase.AUDIT not in load_state(project).completed:
        return render_error(request, 404, t("errors.no_evidence.title"),
                            t("parity_page.evidence_missing"))
    path = current_pack(project, project.ledger.events())
    if path is None:
        return render_error(request, 404, t("errors.no_evidence.title"), outside_console())
    return FileResponse(path, media_type="application/zip", filename=path.name)
