"""Projects list and the new-project form (`create_project`, as `reverseai init`)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from reverseai import pipeline
from reverseai.console.forms import (
    JURISDICTIONS,
    MODE_OPTIONS,
    FormError,
    NewProjectForm,
    intake_message,
)
from reverseai.console.read.projects import project_rows
from reverseai.console.routes import console, require_csrf
from reverseai.console.templating import project_path, render
from reverseai.project import IntakeError, create_project, project_lock

router = APIRouter()


def _display_path(path: Path) -> str:
    """The projects root as shown on the page: the home directory is abbreviated to `~`."""
    try:
        return "~/" + path.resolve().relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return str(path)


@router.get("/")
def projects(request: Request) -> Response:
    ctx = console(request)
    return render(request, "projects.html", active="projects", rows=project_rows(ctx.projects),
                  root=_display_path(ctx.projects.root))


def _form_page(request: Request, form: NewProjectForm, error: str | None = None,
               status_code: int = 200) -> Response:
    return render(request, "project_new.html", status_code, active="projects", form=form,
                  error=error, modes=MODE_OPTIONS, jurisdictions=JURISDICTIONS)


@router.get("/projects/new")
def new_project(request: Request) -> Response:
    return _form_page(request, NewProjectForm())


@router.post("/projects")
def create(
    request: Request,
    csrf: str = Form(""),
    name: str = Form(""),
    mode: str = Form("legacy"),
    target_base_url: str = Form(""),
    allowed_domains: str = Form(""),
    target_is_sandbox: str = Form(""),
    product_name: str = Form(""),
    brand_terms: str = Form(""),
    jurisdictions: Annotated[list[str] | None, Form()] = None,
    jurisdiction: str = Form("RU"),
    lawful_access: str = Form(""),
    basis: str = Form(""),
    signed_by: str = Form(""),
    signed_at: str = Form(""),
) -> Response:
    require_csrf(request, csrf)
    ctx = console(request)
    form = NewProjectForm(
        name=name, mode=mode, target_base_url=target_base_url, allowed_domains=allowed_domains,
        target_is_sandbox=bool(target_is_sandbox), product_name=product_name,
        brand_terms=brand_terms, jurisdictions=jurisdictions or [], jurisdiction=jurisdiction,
        lawful_access=bool(lawful_access), basis=basis, signed_by=signed_by,
        signed_at=signed_at,
    )
    try:
        project = create_project(form.card(), ctx.projects.root)
    except FormError as exc:
        return _form_page(request, form, str(exc), 400)
    except IntakeError as exc:
        return _form_page(request, form, intake_message(exc), 400)
    with project_lock(project.dir):  # a brand-new directory: nobody else holds it
        pipeline.save_state(project, pipeline.load_state(project))  # logs intake, as `init`
    return RedirectResponse(project_path(project.dir.name), status_code=303)
