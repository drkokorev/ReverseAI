"""The projects list: mode, target host, progress over the nine phases, last activity."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from reverseai.console.registry import ProjectInvalid, ProjectRegistry
from reverseai.i18n import Labels
from reverseai.pipeline import Phase, load_state
from reverseai.project import Mode, Project

MODE_LABELS: Labels[Mode] = Labels("mode", list(Mode))


@dataclass
class ProjectRow:
    name: str  # directory name, used in URLs
    title: str
    product: str
    mode: str
    host: str
    sandbox: bool
    done: list[bool]  # per phase, in pipeline order
    last_activity: str | None
    problem: str | None = None  # why the project cannot be read (then only `name` is real)

    @property
    def done_count(self) -> int:
        return sum(self.done)


def target_host(project: Project) -> str:
    return urlsplit(project.card.target_base_url).netloc or project.card.target_base_url


def project_row(name: str, project: Project) -> ProjectRow:
    completed = set(load_state(project).completed)
    events = project.ledger.events()
    card = project.card
    return ProjectRow(
        name=name,
        title=card.name,
        product=card.product_name,
        mode=MODE_LABELS[card.mode],
        host=target_host(project),
        sandbox=card.target_is_sandbox,
        done=[phase in completed for phase in Phase],
        last_activity=events[-1].ts if events else None,
    )


def broken_row(name: str, problem: str) -> ProjectRow:
    return ProjectRow(name=name, title=name, product="", mode="", host="", sandbox=False,
                      done=[False] * len(Phase), last_activity=None, problem=problem)


def project_rows(registry: ProjectRegistry) -> list[ProjectRow]:
    """One row per project; a project that cannot be read is listed with the reason."""
    rows: list[ProjectRow] = []
    for name in registry.names():
        try:
            rows.append(project_row(name, registry.get(name)))
        except ProjectInvalid as exc:
            rows.append(broken_row(name, exc.reason))
    return rows
