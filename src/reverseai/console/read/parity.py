"""Parity and evidence: the parity report, code similarity, brand mentions, the evidence pack."""

from __future__ import annotations

import inspect
import io
import zipfile
from dataclasses import dataclass, field

from reverseai.audit.similarity import brand_mentions
from reverseai.console.artifacts import ArtifactCache
from reverseai.console.evidence import current_pack, evidence_files, similarity_report
from reverseai.parity.differential import (
    MAX_UNSTABLE_SHARE,
    ParityReport,
    meets_threshold,
)
from reverseai.pipeline import Phase, PipelineState, load_state
from reverseai.project import Project
from reverseai.provenance.ledger import LedgerEvent

# The gate's own defaults, shown next to the ratios.
_GATE = inspect.signature(meets_threshold).parameters
PARITY_THRESHOLD: float = _GATE["overall"].default
CRITICAL_THRESHOLD: float = _GATE["critical"].default


def parity_report(
    cache: ArtifactCache, project: Project, state: PipelineState
) -> ParityReport | None:
    ref = state.refs.get("parity_report")
    if ref is None:
        return None
    return ParityReport.model_validate(cache.json(project, ref))


def audited_similarity(
    project: Project, state: PipelineState, events: list[LedgerEvent]
) -> dict | None:
    """The console pack's similarity report, while the audit phase stands and the pack is
    the latest audit's (not one left over before an audit with another `--out`)."""
    if Phase.AUDIT not in state.completed or current_pack(project, events) is None:
        return None
    return similarity_report(project)


def audited_outside(project: Project, state: PipelineState, events: list[LedgerEvent]) -> bool:
    """The audit stands, but its pack is not in the console's evidence directory."""
    return Phase.AUDIT in state.completed and current_pack(project, events) is None


def _code_files(data: bytes) -> dict[str, str]:
    files: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            try:
                files[info.filename] = archive.read(info).decode("utf-8")
            except UnicodeDecodeError:
                continue
    return files


def _latest(events: list[LedgerEvent], type_: str) -> LedgerEvent | None:
    return next((e for e in reversed(events) if e.type == type_), None)


@dataclass
class EvidenceView:
    zip_name: str
    sha256: str | None
    files: list[tuple[str, str]]


@dataclass
class ParityView:
    report: ParityReport | None
    rounds: int
    met: bool
    similarity: dict | None
    brand_hits: list[str] = field(default_factory=list)
    evidence: EvidenceView | None = None
    sandbox_isolated: bool | None = None  # None: implementation never ran
    outside: bool = False  # audited, but the pack was written outside the console
    unstable_limit: float = MAX_UNSTABLE_SHARE
    parity_threshold: float = PARITY_THRESHOLD
    critical_threshold: float = CRITICAL_THRESHOLD

    @property
    def meter_percent(self) -> float:
        """Similarity on a 0..2×threshold scale, as a percentage of the meter width."""
        if not self.similarity:
            return 0.0
        scale = 2 * float(self.similarity["threshold"]) or 1.0
        return min(100.0, 100.0 * float(self.similarity["max_score"]) / scale)


def parity_view(cache: ArtifactCache, project: Project) -> ParityView:
    state = load_state(project)
    events = project.ledger.events()
    report = parity_report(cache, project, state)
    similarity = audited_similarity(project, state, events)
    view = ParityView(
        report=report,
        rounds=state.parity_rounds,
        met=report is not None and meets_threshold(report),
        similarity=similarity,
    )
    start = _latest(events, "implement.start")
    if start is not None:
        view.sandbox_isolated = bool(start.payload.get("sandbox_isolated"))
    if similarity is not None and "code" in state.refs:
        code = _code_files(cache.raw(project, state.refs["code"]))
        view.brand_hits = brand_mentions(code, project.card.brand_terms)
    zip_path = current_pack(project, events)
    view.outside = audited_outside(project, state, events)
    if Phase.AUDIT in state.completed and zip_path is not None:
        packed = _latest(events, "audit.evidence_pack")
        view.evidence = EvidenceView(
            zip_name=zip_path.name,
            sha256=str(packed.payload.get("sha256")) if packed else None,
            files=evidence_files(project),
        )
    return view
