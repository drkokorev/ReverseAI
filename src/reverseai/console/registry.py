"""The projects under `--projects-root`, read from disk on every request and for every job.

A fresh `Project` per use means edits to `card.json` (brand terms, `target_is_sandbox`) apply
to the next page view and job exactly as they apply to the next CLI command. Several `Project`
instances of one directory are safe (D-014): the ledger and the artifact store append under
file locks and re-read the tail from disk, so the hash chain never forks. Mutating work (jobs,
approval) additionally holds the project lock `<project>/pipeline.lock` (D-015), shared with
the CLI's commands.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from reverseai.i18n import t
from reverseai.messages import validation_summary
from reverseai.pipeline import load_state
from reverseai.project import Project


class ProjectNotFound(LookupError):
    """No project of that name under the projects root."""


class ProjectInvalid(ValueError):
    """The project's card or pipeline state cannot be read; `reason` is one translated line."""

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(f"project {name!r} is unreadable: {reason}")
        self.name = name
        self.reason = reason


def _problem(exc: BaseException) -> str:
    if isinstance(exc, ValidationError):
        return validation_summary(exc)
    if isinstance(exc, OSError):
        return t("registry.unreadable_file", error=exc.strerror or type(exc).__name__)
    lines = str(exc).splitlines()
    return lines[0] if lines else type(exc).__name__


class ProjectRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def names(self) -> list[str]:
        """Directory names of the projects (a project is a child directory with card.json)."""
        if not self.root.is_dir():
            return []
        return sorted(
            child.name
            for child in self.root.iterdir()
            if child.is_dir() and not child.name.startswith(".") and (child / "card.json").is_file()
        )

    def get(self, name: str) -> Project:
        """The project called `name`, freshly loaded; only names listed by `names()` are accepted.

        Raises `ProjectNotFound` for other names and `ProjectInvalid` when its card or its
        pipeline state (`state.json`) cannot be read.
        """
        if name not in self.names():
            raise ProjectNotFound(name)
        try:
            project = Project.load(self.root / name)
        except (ValidationError, ValueError, OSError) as exc:
            raise ProjectInvalid(name, t("registry.bad_card", problem=_problem(exc))) from exc
        try:
            load_state(project)
        except (ValidationError, ValueError, OSError) as exc:
            raise ProjectInvalid(name, t("registry.bad_state", problem=_problem(exc))) from exc
        return project
