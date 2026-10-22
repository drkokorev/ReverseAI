"""Project overview: phase timeline, KPIs, zones, ledger events and integrity."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from reverseai.console.artifacts import ArtifactCache
from reverseai.console.read.costs import summarize_costs
from reverseai.console.read.parity import (
    audited_outside,
    audited_similarity,
    parity_report,
)
from reverseai.console.roles import role_label
from reverseai.console.templating import parse_time
from reverseai.i18n import Labels, t
from reverseai.messages import PHASE_LABELS
from reverseai.pipeline import PREREQUISITES, Phase, PipelineState, load_state
from reverseai.project import Project, risk_flags
from reverseai.provenance.ledger import LedgerEvent, LedgerVerification
from reverseai.spec.model import BehaviorSpec
from reverseai.zones.store import Zone

STAGE_NAMES: Labels[Phase] = Labels("stage", list(Phase))
STAGE_ZONES: dict[Phase, Zone] = {
    Phase.INTAKE: Zone.DIRTY,
    Phase.OBSERVE: Zone.DIRTY,
    Phase.ORACLE: Zone.DIRTY,
    Phase.SPEC: Zone.DIRTY,
    Phase.PREPARE_RELEASE: Zone.DIRTY,
    Phase.RELEASE: Zone.RELEASED,
    Phase.IMPLEMENT: Zone.CLEAN,
    Phase.PARITY: Zone.VERIFIER,
    Phase.AUDIT: Zone.VERIFIER,
}
ZONE_NOTES: Labels[Zone] = Labels("zone_note", list(Zone))
LEDGER_LIMIT = 50  # rows shown by default; `?all=1` shows every event
ARTIFACT_PREFIX = "artifact."  # hidden by default (`?artifacts=1` or this type prefix shows them)
SUMMARY_LENGTH = 100
_HASH = re.compile(r"^[0-9a-f]{32,}$")


@dataclass
class Stage:
    num: str
    phase: Phase
    name: str
    label: str
    zone: str
    done: bool
    ready: bool  # its prerequisite is completed (it can run now)
    time: str | None = None
    detail: str = ""


@dataclass
class Kpi:
    key: str
    label: str
    value: str
    sub: str


@dataclass
class ZoneRow:
    zone: str
    note: str
    count: int


@dataclass
class LedgerRow:
    ts: str
    type: str
    zone: str
    actor: str
    hash: str
    summary: str = ""


@dataclass
class Overview:
    state: PipelineState
    stages: list[Stage]
    kpis: list[Kpi]
    zones: list[ZoneRow]
    ledger: list[LedgerRow]
    ledger_total: int
    ledger_shown: int
    integrity: LedgerVerification
    show_artifacts: bool = False
    hidden_artifacts: int = 0  # artifact.* events left out of the listing
    first_ts: str | None = None
    last_ts: str | None = None
    risk_flags: list[str] = field(default_factory=list)

    def stage(self, phase: str) -> Stage:
        return next(s for s in self.stages if s.phase.value == phase)

    @property
    def elapsed(self) -> str:
        start, end = parse_time(self.first_ts), parse_time(self.last_ts)
        if not start or not end:
            return "T+00:00"
        seconds = int((end - start).total_seconds())
        hours, rest = divmod(seconds, 3600)
        minutes, secs = divmod(rest, 60)
        return f"T+{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"T+{minutes:02d}:{secs:02d}"


def _latest(events: list[LedgerEvent], type_: str) -> LedgerEvent | None:
    return next((e for e in reversed(events) if e.type == type_), None)


class _Details:
    """One-line detail per completed phase, from the ledger and (cached) artifacts."""

    def __init__(self, cache: ArtifactCache, project: Project, state: PipelineState,
                 events: list[LedgerEvent]) -> None:
        self.cache, self.project, self.state, self.events = cache, project, state, events

    def _json(self, key: str):
        ref = self.state.refs.get(key)
        return self.cache.json(self.project, ref) if ref else None

    def intake(self) -> str:
        flags = risk_flags(self.project.card)
        return t("detail.intake", flags=", ".join(flags) if flags else t("detail.no_risks"))

    def observe(self) -> str:
        pages = self._json("pages") or []
        exchanges = self._json("exchanges") or []
        probes = self._json("probe_exchanges") or []
        return ", ".join([t("detail.pages", count=len(pages)),
                          t("detail.exchanges", count=len(exchanges)),
                          t("detail.probes", count=len(probes))])

    def oracle(self) -> str:
        scenarios = self._json("scenarios") or []
        text = t("detail.scenarios", count=len(scenarios))
        dropped = self._json("oracle_unstable")
        if dropped is not None:
            text += ", " + t("detail.dropped", count=len(dropped))
        return text

    def spec(self) -> str:
        data = self._json("spec")
        if data is None:
            return ""
        spec = BehaviorSpec.model_validate(data)
        return ", ".join([t("detail.features", count=len(spec.features)),
                          t("detail.rules", count=len(spec.rules))])

    def prepare_release(self) -> str:
        event = _latest(self.events, "barrier.prepared")
        if event is None:
            return ""
        return t("detail.findings", count=int(event.payload.get("findings", 0)))

    def release(self) -> str:
        event = _latest(self.events, "barrier.approved")
        if event is None:
            return ""
        return t("detail.signed", sha=str(event.payload.get("package_sha256", ""))[:6])

    def implement(self) -> str:
        event = _latest(self.events, "implement.iteration")
        done = _latest(self.events, "implement.done")
        if event is None or done is None:
            return ""
        iterations = int(done.payload.get("iterations", 0))
        return ", ".join([t("detail.iterations", count=iterations),
                          t("common.of", part=event.payload.get("passed"),
                            whole=event.payload.get("total"))])

    def parity(self) -> str:
        report = parity_report(self.cache, self.project, self.state)
        if report is None:
            return ""
        rounds = self.state.parity_rounds
        return t("detail.parity", ratio=report.ratio, count=rounds)

    def audit(self) -> str:
        similarity = audited_similarity(self.project, self.state, self.events)
        if similarity is None:
            if audited_outside(self.project, self.state, self.events):
                return t("detail.audit_outside")
            return ""
        return t("detail.similarity", score=float(similarity["max_score"]))

    def __call__(self, phase: Phase) -> str:
        return getattr(self, phase.value)()


def stages(cache: ArtifactCache, project: Project, state: PipelineState,
           events: list[LedgerEvent]) -> list[Stage]:
    completed_at: dict[str, str] = {}
    for event in events:
        if event.type == "phase.completed":
            completed_at[str(event.payload.get("phase"))] = event.ts
    details = _Details(cache, project, state, events)
    result: list[Stage] = []
    for n, phase in enumerate(Phase, start=1):
        done = phase in state.completed
        needed = PREREQUISITES.get(phase)
        result.append(
            Stage(
                num=f"{n:02d}",
                phase=phase,
                name=STAGE_NAMES[phase],
                label=PHASE_LABELS[phase],
                zone=STAGE_ZONES[phase].value,
                done=done,
                ready=needed is None or needed in state.completed,
                time=completed_at.get(phase.value) if done else None,
                detail=details(phase) if done else "",
            )
        )
    return result


def kpis(cache: ArtifactCache, project: Project, state: PipelineState,
         events: list[LedgerEvent]) -> list[Kpi]:
    report = parity_report(cache, project, state)
    parity_label, critical_label = t("kpi.parity"), t("kpi.critical")
    if report is not None:
        parity = Kpi("parity", parity_label, f"{report.ratio:.3f}",
                     t("kpi.scenarios_passed", passed=report.passed, count=report.total))
        critical = Kpi("critical", critical_label, f"{report.critical_ratio:.3f}",
                       t("common.of", part=report.critical_passed, whole=report.critical_total))
    else:
        parity = Kpi("parity", parity_label, "—", t("kpi.no_report"))
        critical = Kpi("critical", critical_label, "—", t("kpi.no_report"))
    similarity = audited_similarity(project, state, events)
    code_label = t("kpi.similarity")
    if similarity is not None:
        code = Kpi("similarity", code_label, f"{float(similarity['max_score']):.3f}",
                   t("kpi.threshold", threshold=float(similarity["threshold"])))
    elif audited_outside(project, state, events):
        code = Kpi("similarity", code_label, "—", t("kpi.audit_outside"))
    else:
        code = Kpi("similarity", code_label, "—", t("kpi.no_audit"))
    costs = summarize_costs(events)
    llm = Kpi("llm", "LLM", f"${costs.total_usd:.4f}", t("kpi.calls", count=costs.calls))
    return [parity, critical, code, llm]


def _number(value: float) -> str:
    return f"{value:.4g}" if isinstance(value, float) else str(value)


def event_summary(event: LedgerEvent) -> str:
    """One line from the payload: phase, approver and role, kind:name, model and cost, counts.

    Hashes and artifact ids are left out (the row has the event hash); long lines are cut.
    """
    p: dict[str, Any] = event.payload
    parts: list[str] = []
    if "phase" in p:
        parts.append(t("summary.phase", phase=p["phase"]))
    if isinstance(p.get("invalidated"), list):
        parts.append(t("summary.invalidated", phases=", ".join(str(x) for x in p["invalidated"])))
    if "approver" in p:
        parts.append(f"{p['approver']} · {role_label(str(p.get('role', '')))}")
    if "model" in p:
        llm = f"{p.get('role', '—')} · {p['model']}"
        if isinstance(p.get("cost_usd"), int | float):
            llm += f" · ${float(p['cost_usd']):.4f}"
        parts.append(llm)
    elif "kind" in p:
        kind = f"{p['kind']}:{p['name']}" if "name" in p else str(p["kind"])
        if "reader" in p:
            kind += f" ← {p['reader']}"
        parts.append(kind)
    skip = {"phase", "invalidated", "approver", "role", "model", "cost_usd", "kind", "name",
            "reader", "size", "seq"}
    for key, value in p.items():
        if key in skip or isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            parts.append(f"{key}={_number(value)}")
        elif isinstance(value, list) and value:
            parts.append(f"{key}={len(value)}")
    if not parts:  # e.g. project.created: a few short plain strings
        parts = [f"{k}={v}" for k, v in p.items()
                 if isinstance(v, str) and len(v) <= 40 and not _HASH.match(v)][:3]
    text = ", ".join(parts)
    if len(text) > SUMMARY_LENGTH:
        text = text[: SUMMARY_LENGTH - 1] + "…"
    return text


def _listed(event: LedgerEvent, type_prefix: str, show_artifacts: bool) -> bool:
    if not event.type.startswith(type_prefix):
        return False
    hidden = not show_artifacts and not type_prefix.startswith(ARTIFACT_PREFIX)
    return not (hidden and event.type.startswith(ARTIFACT_PREFIX))


def ledger_rows(
    events: list[LedgerEvent], type_prefix: str = "", limit: int | None = LEDGER_LIMIT,
    show_artifacts: bool = False,
) -> list[LedgerRow]:
    """Latest first; artifact.* events only with `show_artifacts` or an `artifact.` prefix."""
    rows = [
        LedgerRow(ts=e.ts, type=e.type, zone=e.zone, actor=e.actor, hash=e.hash,
                  summary=event_summary(e))
        for e in reversed(events)
        if _listed(e, type_prefix, show_artifacts)
    ]
    return rows if limit is None else rows[:limit]


def overview(
    cache: ArtifactCache, project: Project, type_prefix: str = "",
    limit: int | None = LEDGER_LIMIT, show_artifacts: bool = False,
) -> Overview:
    state = load_state(project)
    events = project.ledger.events()
    integrity = project.ledger.verify()
    completed = [e.ts for e in events if e.type == "phase.completed"]
    rows = ledger_rows(events, type_prefix, limit, show_artifacts)
    matching = [e for e in events if e.type.startswith(type_prefix)]
    listed = sum(_listed(e, type_prefix, show_artifacts) for e in matching)
    return Overview(
        state=state,
        stages=stages(cache, project, state, events),
        kpis=kpis(cache, project, state, events),
        zones=[ZoneRow(z.value, ZONE_NOTES[z], len(project.store.list(z))) for z in Zone],
        ledger=rows,
        ledger_total=listed,
        ledger_shown=len(rows),
        integrity=integrity,
        show_artifacts=show_artifacts,
        hidden_artifacts=len(matching) - listed,
        first_ts=completed[0] if completed else None,
        last_ts=completed[-1] if completed else None,
        risk_flags=risk_flags(project.card),
    )
