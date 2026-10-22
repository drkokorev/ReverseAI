"""Release review: the sanitized draft (spec, scenarios, cleanup report) and its approval."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from reverseai.barrier.release import PreparedRelease
from reverseai.barrier.sanitizer import WARNING_KINDS, Finding, withheld_expectations
from reverseai.console.artifacts import ArtifactCache
from reverseai.i18n import Labels
from reverseai.oracle.model import Scenario
from reverseai.pipeline import Phase, load_state, release_draft_path
from reverseai.project import Project

# body_warning (D-012) is shown to the approver, never blocking.
FINDING_KINDS: Labels[str] = Labels("finding", ["code", "verbatim", "brand", "url", "body_warning"])
TABS: Labels[str] = Labels("release_page.tab", ["spec", "scenarios", "cleanup"])


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass
class Withheld:
    scenario: str
    step: int  # 1-based
    pointer: str


@dataclass
class ReleaseView:
    draft: PreparedRelease | None
    markdown_path: str | None
    withheld: list[Withheld] = field(default_factory=list)
    dropped: list[str] | None = None  # scenarios the oracle dropped (None: no reset replay)
    approval: dict | None = None  # of the released package, once released
    released: bool = False

    @property
    def findings(self) -> list[Finding]:
        """What the sanitizer changed (blocking kinds), without the body warnings."""
        if self.draft is None:
            return []
        return [f for f in self.draft.report.findings if f.kind not in WARNING_KINDS]

    @property
    def warnings(self) -> list[Finding]:
        """Request-body strings that match the original: kept as sent, shown to the approver."""
        if self.draft is None:
            return []
        return [f for f in self.draft.report.findings if f.kind in WARNING_KINDS]


def _withheld(full: list[Scenario], released: list[Scenario]) -> list[Withheld]:
    return [
        Withheld(before.id, step + 1, pointer)
        for before, after in zip(full, released, strict=False)
        for step, pointer in withheld_expectations(before, after)
    ]


def release_view(cache: ArtifactCache, project: Project) -> ReleaseView:
    state = load_state(project)
    if "release_draft" not in state.refs:
        return ReleaseView(draft=None, markdown_path=None)
    draft = PreparedRelease.model_validate(cache.json(project, state.refs["release_draft"]))
    draft_file = release_draft_path(project)
    view = ReleaseView(draft=draft, markdown_path=f"{project.dir.name}/{draft_file.name}")
    if "scenarios" in state.refs:
        full = [Scenario.model_validate(s) for s in cache.json(project, state.refs["scenarios"])]
        view.withheld = _withheld(full, draft.scenarios)
    if "oracle_unstable" in state.refs:
        view.dropped = list(cache.json(project, state.refs["oracle_unstable"]))
    if Phase.RELEASE in state.completed and "release" in state.refs:
        view.released = True
        view.approval = cache.json(project, state.refs["release"]).get("approval")
    return view
