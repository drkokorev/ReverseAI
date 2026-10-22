"""Release review page and approval at the barrier (`run_release`, as `reverseai approve`)."""

from __future__ import annotations

from fastapi import APIRouter, Form
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from reverseai.barrier.release import ReleaseError
from reverseai.console import actions
from reverseai.console.read.release import FINDING_KINDS, TABS, compact, release_view
from reverseai.console.roles import CONSOLE_ROLES, role_label
from reverseai.console.routes import console, require_csrf
from reverseai.console.templating import project_path, render
from reverseai.i18n import t
from reverseai.messages import PlainError, user_message
from reverseai.pipeline import PhaseOrderError
from reverseai.project import ProjectBusy

router = APIRouter()


def _page(
    request: Request,
    name: str,
    *,
    tab: str = "spec",
    error: str | None = None,
    status_code: int = 200,
    approver: str = "",
    role: str = "operator",
) -> Response:
    ctx = console(request)
    project = ctx.projects.get(name)
    view = release_view(ctx.artifacts, project)
    job = ctx.jobs.current(name)
    return render(
        request,
        "release.html",
        status_code,
        active="release",
        project_name=name,
        card=project.card,
        view=view,
        tab=tab if tab in TABS else "spec",
        tabs=TABS,
        roles=CONSOLE_ROLES,
        role_label=role_label,
        finding_kinds=FINDING_KINDS,
        compact=compact,
        error=error,
        approver=approver or (ctx.operator or ""),
        role=role if role in CONSOLE_ROLES else "operator",
        busy=job is not None and job.running,
    )


@router.get("/projects/{name}/release")
def release_page(request: Request, name: str, tab: str = "spec") -> Response:
    return _page(request, name, tab=tab)


@router.post("/projects/{name}/release/approve")
def approve(
    request: Request,
    name: str,
    csrf: str = Form(""),
    approver: str = Form(""),
    role: str = Form(""),
    confirm: str = Form(""),
    sha: str = Form(""),
) -> Response:
    require_csrf(request, csrf)
    ctx = console(request)
    project = ctx.projects.get(name)

    def refuse(message: str, status_code: int) -> Response:
        return _page(request, name, error=message, status_code=status_code,
                     approver=approver, role=role)

    if not approver.strip():
        return refuse(t("approve.approver_required"), 400)
    if role not in CONSOLE_ROLES:
        return refuse(t("approve.unknown_role"), 400)
    if not confirm:
        return refuse(t("approve.confirm_required"), 400)
    job = ctx.jobs.current(name)
    if job is not None and job.running:
        return refuse(t("approve.wait_job", label=job.label), 409)
    try:
        actions.approve(project, approver=approver.strip(), role=role, sha=sha.strip())
    except (PhaseOrderError, ReleaseError, PlainError, ProjectBusy) as exc:
        return refuse(t("cli.error", message=user_message(exc)), 409)
    return RedirectResponse(f"{project_path(name)}/release", status_code=303)
