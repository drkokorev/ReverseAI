"""LLM costs page (the numbers of `reverseai costs`)."""

from __future__ import annotations

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response

from reverseai.console.read.costs import summarize_costs
from reverseai.console.routes import console
from reverseai.console.templating import render

router = APIRouter()


@router.get("/projects/{name}/costs")
def costs_page(request: Request, name: str) -> Response:
    project = console(request).projects.get(name)
    return render(request, "costs.html", active="costs", project_name=name, card=project.card,
                  costs=summarize_costs(project.ledger.events()))
