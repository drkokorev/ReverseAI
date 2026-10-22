"""Project intake: the legal gate and the on-disk project layout."""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from reverseai.i18n import has, t
from reverseai.llm.policy import DataPolicy
from reverseai.provenance.ledger import Ledger
from reverseai.zones.store import ArtifactStore

try:  # POSIX; elsewhere the project lock is not enforced
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

_ACTOR = "intake"
LOCK_FILE = "pipeline.lock"
_MIN_BRAND_TOKEN = 4  # shorter shared words ("pro", "lite") are too generic to be a brand hit
_INITIAL_STATE = {"completed": [], "refs": {}, "parity_rounds": 0}


class IntakeError(Exception):
    """The project card fails the legal/intake gate.

    `key` names the refusal (catalog entry `intake.<key>`), `params` fill it in; the message
    is in the language active when the error is raised. Any other text is taken as the
    message itself.
    """

    def __init__(self, key: str, **params: object) -> None:
        entry = f"intake.{key}"
        super().__init__(t(entry, **params) if has(entry) else key)
        self.key = key
        self.params = params


class ProjectBusy(RuntimeError):
    """Another command or console job holds the project lock (the message is translated)."""

    def __init__(self, project_dir: Path) -> None:
        super().__init__(t("project.busy", path=project_dir))
        self.project_dir = project_dir


@contextlib.contextmanager
def project_lock(project_dir: Path) -> Iterator[None]:
    """Hold the project's lock (`<project>/pipeline.lock`, D-015) or fail at once.

    Every mutating entry point (CLI commands, console jobs and approval) runs under it, so two
    of them never interleave their read-modify-write of `state.json` and the phase artifacts.
    The lock is an exclusive non-blocking `flock`: a second holder in any process (or another
    open of the file in this process) gets `ProjectBusy` instead of waiting. The kernel drops
    it when the holder exits, so a crashed command never leaves the project locked.
    """
    path = Path(project_dir) / LOCK_FILE
    with path.open("ab") as handle:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ProjectBusy(Path(project_dir)) from None
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Mode(StrEnum):
    LEGACY = "legacy"
    IMPORT_SUBSTITUTION = "import_substitution"


class Attestation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lawful_access: bool
    basis: str
    signed_by: str
    signed_at: str


class ProjectCard(BaseModel):
    # A misspelled key (`brand_term`, `target_is_sanbox`) must fail intake: silently ignored,
    # it would drop brand masking or flip a safety flag back to its default.
    model_config = ConfigDict(extra="forbid")

    name: str
    mode: Mode
    target_base_url: str
    allowed_domains: list[str]
    target_is_sandbox: bool = False
    attestation: Attestation
    data_policy: DataPolicy = Field(default_factory=DataPolicy)
    jurisdiction: str = "RU"
    brand_terms: list[str] = Field(default_factory=list)
    product_name: str
    target_stack: str = "python-fastapi"

    @field_validator("data_policy", mode="before")
    @classmethod
    def _policy_from_json(cls, value: object) -> object:
        if isinstance(value, dict) and "allowed_jurisdictions" in value:
            return DataPolicy(allowed_jurisdictions=set(value["allowed_jurisdictions"]))
        return value

    @field_serializer("data_policy")
    def _policy_to_json(self, policy: DataPolicy) -> dict:
        return {"allowed_jurisdictions": sorted(policy.allowed_jurisdictions)}


def risk_flags(card: ProjectCard) -> list[str]:
    flags: list[str] = []
    if card.mode == Mode.IMPORT_SUBSTITUTION:
        flags += ["patents", "trademarks", "tos_review"]
    if not card.target_is_sandbox:
        flags.append("read_only_observation")
    return flags


def slug(name: str) -> str:
    result = re.sub(r"[\W_]+", "-", name.lower()).strip("-")
    if not result:
        raise IntakeError("no_usable_characters", name=name)
    return result


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[\W_]+", text.lower()) if t}


def _reuses_brand(product_name: str, brand_terms: list[str]) -> bool:
    product = product_name.lower()
    product_tokens = _tokens(product_name)
    for term in brand_terms:
        term_l = term.lower().strip()
        if not term_l:
            continue
        if term_l in product:
            return True
        if any(len(t) >= _MIN_BRAND_TOKEN and t in product_tokens for t in _tokens(term)):
            return True
    return False


def _validate(card: ProjectCard) -> None:
    if not card.attestation.lawful_access:
        raise IntakeError("attestation_required")
    host = (urlparse(card.target_base_url).hostname or "").lower()
    allowed = {d.lower() for d in card.allowed_domains}
    if not host or host not in allowed:
        raise IntakeError("host_not_allowed", host=host)
    if _reuses_brand(card.product_name, card.brand_terms):
        raise IntakeError("product_reuses_brand", name=card.product_name)


class Project:
    def __init__(self, root: Path) -> None:
        self.dir = Path(root)
        self.card = ProjectCard.model_validate_json(
            (self.dir / "card.json").read_text(encoding="utf-8")
        )
        self.ledger = Ledger(self.dir / "ledger.jsonl")
        self.store = ArtifactStore(self.dir / "artifacts", self.ledger)

    @classmethod
    def load(cls, path: Path) -> Project:
        return cls(path)


def create_project(card: ProjectCard, projects_root: Path) -> Project:
    _validate(card)
    project_dir = Path(projects_root) / slug(card.name)
    if project_dir.exists():
        raise IntakeError("project_exists", path=project_dir)
    project_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        project_dir.mkdir()  # atomic: whoever creates it first owns the project
    except FileExistsError:
        raise IntakeError("project_exists", path=project_dir) from None
    (project_dir / "card.json").write_text(
        card.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (project_dir / "state.json").write_text(
        json.dumps(_INITIAL_STATE, indent=2) + "\n", encoding="utf-8"
    )
    project = Project(project_dir)
    project.ledger.append(
        "project.created",
        "dirty",
        _ACTOR,
        {
            "name": card.name,
            "mode": card.mode.value,
            "risk_flags": risk_flags(card),
            "attestation": card.attestation.model_dump(),
        },
    )
    return project
