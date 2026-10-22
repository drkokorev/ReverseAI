"""Starting pipeline phases as background jobs, and the job status endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Form
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from reverseai.console import actions
from reverseai.console.forms import FormError, positive_int
from reverseai.console.jobs import Action, Job, JobBusy
from reverseai.console.routes import console, require_csrf
from reverseai.console.routes.overview import render_overview
from reverseai.console.templating import project_path, render_error
from reverseai.i18n import t
from reverseai.messages import user_message
from reverseai.project import ProjectBusy

router = APIRouter()
ensure_free = actions.ensure_free


def _busy(request: Request, name: str, job: Job) -> Response:
    return render_overview(
        request, name, status_code=409,
        error=t("phases.busy", label=job.label),
    )


@router.post("/projects/{name}/run/{action}")
def run_phase(
    request: Request,
    name: str,
    action: str,
    csrf: str = Form(""),
    max_pages: str = Form(""),
    submit_forms: str = Form(""),
    probe: str = Form(""),
    max_rounds: str = Form(""),
    allow_unstable: str = Form(""),
) -> Response:
    require_csrf(request, csrf)
    ctx = console(request)
    project = ctx.projects.get(name)
    if action not in actions.RUNNABLE:
        return render_error(request, 404, t("errors.no_action.title"),
                            t("errors.no_action.message", action=action))
    try:
        work: Action
        if action == "observe":
            work = actions.observe_job(
                project,
                max_pages=positive_int(max_pages, 50, t("phases.bad_max_pages")),
                submit_forms=bool(submit_forms),
                probe=bool(probe),
            )
        elif action == "oracle":
            work = actions.oracle_job(project)
        elif action == "spec":
            work = actions.spec_job(project, ctx.gateway_factory)
        elif action == "prepare-release":
            work = actions.prepare_release_job(project)
        elif action == "build":
            work = actions.build_job(
                project, ctx.gateway_factory, ctx.sandbox_factory,
                max_rounds=positive_int(max_rounds, 3, t("phases.bad_max_rounds")),
                allow_unstable=bool(allow_unstable),
            )
        else:
            work = actions.audit_job(project)
    except FormError as exc:
        return render_overview(request, name, error=str(exc), status_code=400)
    running = ctx.jobs.current(name)
    if running is not None and running.running:
        return _busy(request, name, running)
    try:
        ensure_free(project)  # another process (the CLI) holds the project
    except ProjectBusy as exc:
        return render_overview(request, name, error=t("cli.error", message=user_message(exc)),
                               status_code=409)
    try:
        ctx.jobs.start(name, action, actions.action_label(action), actions.locked(project, work))
    except JobBusy as busy:
        return _busy(request, name, busy.job)
    return RedirectResponse(f"{project_path(name)}#job", status_code=303)


@router.get("/projects/{name}/job")
def job_status(request: Request, name: str) -> JSONResponse:
    ctx = console(request)
    ctx.projects.get(name)  # 404 for unknown projects
    job = ctx.jobs.current(name)
    return JSONResponse({"job": job.as_json() if job else None})
