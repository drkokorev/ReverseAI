"""Pipeline orchestration: phases, their prerequisites and the state persisted in `state.json`.

Every phase checks that its predecessor completed, stores its outputs as artifacts, records the
artifact ids in `PipelineState.refs` and appends `phase.completed` to the ledger. Re-running a
completed phase is allowed: it replaces its own refs and invalidates every later phase (they are
removed from `completed`, their refs are dropped and `phase.invalidated` is logged), so stale
outputs built from the old inputs can never be used.
"""

from __future__ import annotations

import io
import os
import secrets
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel

from reverseai.audit.evidence import build_evidence_pack
from reverseai.audit.similarity import SimilarityReport, brand_mentions, code_similarity
from reverseai.barrier.release import (
    Approval,
    PreparedRelease,
    expression_index,
    prepare_release,
    release,
    target_domains,
)
from reverseai.config import Settings, load_settings
from reverseai.implement.agent import ImplementConfig, ImplementResult, implement
from reverseai.llm.gateway import Gateway
from reverseai.llm.providers import build_providers
from reverseai.observe.bundle import ObservationBundle
from reverseai.observe.contracts import Endpoint, infer_endpoints
from reverseai.observe.explorer import ExplorerConfig, PageObservation, explore
from reverseai.observe.har import Exchange, parse_har
from reverseai.observe.probe import probe_endpoints
from reverseai.oracle.build import build_scenarios
from reverseai.oracle.model import Scenario
from reverseai.oracle.runner import run_scenarios
from reverseai.parity.differential import ParityReport, meets_threshold, run_parity
from reverseai.parity.feedback import feedback_for_clean_zone
from reverseai.project import IntakeError, Project
from reverseai.sandbox.base import Sandbox, ServiceHandle, free_port
from reverseai.spec.builder import build_spec
from reverseai.spec.model import BehaviorSpec
from reverseai.zones.store import Zone

_ACTOR = "pipeline"
_STATE_FILE = "state.json"
WORKSPACES_DIR = ".workspaces"
RELEASE_DRAFT_MD = "release_draft.md"
_CLONE_MODULE = "main:app"
CLONE_DID_NOT_START = (
    "service did not start: `python -m uvicorn main:app` from the workspace root must serve "
    "HTTP on the given port"
)


class Phase(StrEnum):
    INTAKE = "intake"
    OBSERVE = "observe"
    ORACLE = "oracle"
    SPEC = "spec"
    PREPARE_RELEASE = "prepare_release"
    RELEASE = "release"
    IMPLEMENT = "implement"
    PARITY = "parity"
    AUDIT = "audit"


PREREQUISITES: dict[Phase, Phase] = {
    Phase.OBSERVE: Phase.INTAKE,
    Phase.ORACLE: Phase.OBSERVE,
    Phase.SPEC: Phase.ORACLE,
    Phase.PREPARE_RELEASE: Phase.SPEC,
    Phase.RELEASE: Phase.PREPARE_RELEASE,
    Phase.IMPLEMENT: Phase.RELEASE,
    Phase.PARITY: Phase.IMPLEMENT,
    Phase.AUDIT: Phase.PARITY,
}


# The `PipelineState.refs` keys each phase writes (dropped when the phase is invalidated).
PHASE_REFS: dict[Phase, tuple[str, ...]] = {
    Phase.INTAKE: (),
    Phase.OBSERVE: ("pages", "exchanges", "probe_exchanges", "endpoints", "har"),
    Phase.ORACLE: ("scenarios", "oracle_unstable"),
    Phase.SPEC: ("spec",),
    Phase.PREPARE_RELEASE: ("release_draft", "release_draft_md"),
    Phase.RELEASE: ("release",),
    Phase.IMPLEMENT: ("code",),
    Phase.PARITY: ("parity_report",),
    Phase.AUDIT: (),
}


class PhaseOrderError(RuntimeError):
    """A phase was started before the phase it depends on completed."""

    def __init__(self, missing: Phase):
        super().__init__(f"phase {missing.value!r} must be completed first")
        self.missing = missing


class PipelineState(BaseModel):
    completed: list[Phase]
    refs: dict[str, str]
    parity_rounds: int = 0
    workspace: str | None = None  # the clone workspace (see `workspace_dir`)


def load_state(project: Project) -> PipelineState:
    """Read `state.json`; INTAKE counts as completed for any existing project."""
    path = project.dir / _STATE_FILE
    state = PipelineState.model_validate_json(path.read_text(encoding="utf-8"))
    if Phase.INTAKE not in state.completed:
        state.completed.insert(0, Phase.INTAKE)
    return state


def _persisted_phases(path: Path) -> list[Phase]:
    return PipelineState.model_validate_json(path.read_text(encoding="utf-8")).completed


def save_state(project: Project, state: PipelineState) -> None:
    """Write `state.json`; the first time INTAKE is persisted it is logged as completed."""
    path = project.dir / _STATE_FILE
    newly_intake = Phase.INTAKE in state.completed and (
        not path.exists() or Phase.INTAKE not in _persisted_phases(path)
    )
    tmp = path.with_name(f".{_STATE_FILE}.tmp")
    tmp.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    if newly_intake:
        project.ledger.append(
            "phase.completed", Zone.VERIFIER.value, _ACTOR, {"phase": Phase.INTAKE.value, "refs": {}}
        )


def workspace_dir(project: Project) -> Path:
    """The clone workspace: `<projects root>/.workspaces/<random hex>`, created on first use.

    It lies outside the project directory under a neutral name, so neither the project's
    name nor its dirty-zone files are reachable from (or visible in paths of) the clean zone.
    The path is recorded in `state.json` and reused on later builds.
    """
    state = load_state(project)
    if state.workspace is None:
        root = project.dir.resolve().parent / WORKSPACES_DIR
        state.workspace = str(root / secrets.token_hex(8))
        save_state(project, state)
    path = Path(state.workspace)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _require(project: Project, phase: Phase) -> PipelineState:
    state = load_state(project)
    needed = PREREQUISITES[phase]
    if needed not in state.completed:
        raise PhaseOrderError(needed)
    return state


def _complete(project: Project, phase: Phase, refs: Mapping[str, str]) -> None:
    """Record `refs`, mark `phase` completed and invalidate every later phase.

    The prerequisite is checked again on the state read here: a phase whose predecessor was
    invalidated while it ran (by a command outside the project lock) is not recorded.

    The phase's own refs are replaced by `refs`; later phases leave `completed` and lose their
    refs (`phase.invalidated` lists the ones that had been completed). A stale review markdown
    (`release_draft.md`) is removed so no approver signs a draft that no longer exists.
    """
    state = load_state(project)
    needed = PREREQUISITES.get(phase)
    if needed is not None and needed not in state.completed:
        raise PhaseOrderError(needed)  # invalidated while this phase was running
    order = list(Phase)
    later = order[order.index(phase) + 1 :]
    invalidated = [p for p in later if p in state.completed]
    for stale in (phase, *later):
        for key in PHASE_REFS[stale]:
            state.refs.pop(key, None)
    if Phase.PREPARE_RELEASE in later:
        release_draft_path(project).unlink(missing_ok=True)
    state.refs.update(refs)
    state.completed = [p for p in state.completed if p not in invalidated]
    if phase not in state.completed:
        state.completed.append(phase)
    save_state(project, state)
    if invalidated:
        project.ledger.append(
            "phase.invalidated",
            Zone.VERIFIER.value,
            _ACTOR,
            {"phase": phase.value, "invalidated": [p.value for p in invalidated]},
        )
    project.ledger.append(
        "phase.completed", Zone.VERIFIER.value, _ACTOR, {"phase": phase.value, "refs": dict(refs)}
    )


def _ref(state: PipelineState, key: str) -> str:
    try:
        return state.refs[key]
    except KeyError:
        raise RuntimeError(f"pipeline state has no {key!r} artifact") from None


def _origin(url: str) -> str:
    """scheme://host[:port] of the target: observed paths are absolute."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


# --- observe ------------------------------------------------------------------------------


def record_observation(
    project: Project,
    *,
    pages: list[PageObservation],
    har_exchanges: list[Exchange],
    probe_exchanges: list[Exchange],
    har_ref: str | None = None,
) -> None:
    """Store an observation as DIRTY artifacts and complete the OBSERVE phase.

    Endpoints are inferred over HAR and probe exchanges together.
    """
    _require(project, Phase.OBSERVE)
    store = project.store
    page_refs = [
        store.put_json(Zone.DIRTY, "page", p.url, p.model_dump(mode="json")).id for p in pages
    ]
    exchanges = [*har_exchanges, *probe_exchanges]
    endpoints = infer_endpoints(exchanges)
    refs = {
        "pages": store.put_json(Zone.DIRTY, "page_index", "page_index", page_refs).id,
        "exchanges": store.put_json(
            Zone.DIRTY, "exchanges", "exchanges", [e.model_dump(mode="json") for e in exchanges]
        ).id,
        "probe_exchanges": store.put_json(
            Zone.DIRTY, "probe_exchanges", "probe_exchanges",
            [e.model_dump(mode="json") for e in probe_exchanges],
        ).id,
        "endpoints": store.put_json(
            Zone.DIRTY, "endpoints", "endpoints", [e.model_dump(mode="json") for e in endpoints]
        ).id,
    }
    if har_ref is not None:
        refs["har"] = har_ref
    _complete(project, Phase.OBSERVE, refs)


_DEFAULT_DELAY_S: float = ExplorerConfig.model_fields["delay_s"].default


def run_observe(
    project: Project,
    *,
    max_pages: int = 50,
    submit_forms: bool = False,
    probe: bool = False,
    delay_s: float = _DEFAULT_DELAY_S,
) -> None:
    """Explore the target in a browser, optionally probe its endpoints, store the observation.

    `delay_s` is the pause between requests toward the target, for browsing and probing.
    """
    _require(project, Phase.OBSERVE)
    card = project.card
    if (submit_forms or probe) and not card.target_is_sandbox:
        raise IntakeError("observe_needs_sandbox")
    config = ExplorerConfig(
        start_url=card.target_base_url,
        allowed_domains=card.allowed_domains,
        max_pages=max_pages,
        delay_s=delay_s,
        submit_forms=submit_forms,
    )
    result = explore(config, card, project.store)
    har = project.store.get_json(result.har_ref, Zone.DIRTY)
    har_exchanges = parse_har(har, card.allowed_domains).exchanges
    probe_exchanges: list[Exchange] = []
    if probe:
        probe_exchanges = probe_endpoints(
            _origin(card.target_base_url),
            infer_endpoints(har_exchanges),
            card,
            delay_s=delay_s,
            exchanges=har_exchanges,
            ledger=project.ledger,
        )
    record_observation(
        project,
        pages=result.pages,
        har_exchanges=har_exchanges,
        probe_exchanges=probe_exchanges,
        har_ref=result.har_ref,
    )


def _exchanges(project: Project, ref: str) -> list[Exchange]:
    return [Exchange.model_validate(e) for e in project.store.get_json(ref, Zone.DIRTY)]


def _endpoints(project: Project, ref: str) -> list[Endpoint]:
    return [Endpoint.model_validate(e) for e in project.store.get_json(ref, Zone.DIRTY)]


# --- oracle and spec ----------------------------------------------------------------------


def run_oracle(project: Project, *, reset_original: Callable[[], None] | None = None) -> None:
    """Build executable scenarios from the observed exchanges.

    With `reset_original`, every scenario is replayed on the original from a reset state and
    only those that pass are kept: a scenario recorded against state built up earlier (e.g. a
    409 duplicate of a task created before) is not reproducible, so no clone could satisfy it.
    The dropped ids go to the ledger (`oracle.unstable`) and to an `oracle_unstable` artifact.
    Replaying writes to the target, so it requires `card.target_is_sandbox`. A replay that keeps
    no scenario, or drops every critical one, means a broken reset or an unreachable original:
    RuntimeError, and the phase is not completed.
    """
    state = _require(project, Phase.ORACLE)
    if reset_original is not None and not project.card.target_is_sandbox:
        raise IntakeError("replay_needs_sandbox")
    scenarios = build_scenarios(
        _exchanges(project, _ref(state, "exchanges")),
        _endpoints(project, _ref(state, "endpoints")),
    )
    refs: dict[str, str] = {}
    if reset_original is not None:
        results = run_scenarios(
            scenarios, _origin(project.card.target_base_url), reset=reset_original
        )
        passed = {r.id for r in results if r.passed}
        dropped = [s.id for s in scenarios if s.id not in passed]
        had_critical = any(s.critical for s in scenarios)
        scenarios = [s for s in scenarios if s.id in passed]
        refs["oracle_unstable"] = project.store.put_json(
            Zone.DIRTY, "oracle_unstable", "oracle_unstable", dropped
        ).id
        project.ledger.append(
            "oracle.unstable",
            Zone.DIRTY.value,
            "oracle",
            {"dropped": dropped, "kept": len(scenarios)},
        )
        if not scenarios:
            raise RuntimeError(
                "no scenario reproduced on the reset original: check the reset and that the "
                "target is reachable"
            )
        if had_critical and not any(s.critical for s in scenarios):
            raise RuntimeError(
                "every critical scenario failed on the reset original: check the reset"
            )
    refs["scenarios"] = project.store.put_json(
        Zone.DIRTY, "scenarios", "scenarios", [s.model_dump(mode="json") for s in scenarios]
    ).id
    _complete(project, Phase.ORACLE, refs)


def _bundle(project: Project, state: PipelineState) -> ObservationBundle:
    store = project.store
    page_refs = store.get_json(_ref(state, "pages"), Zone.DIRTY)
    pages = [PageObservation.model_validate(store.get_json(r, Zone.DIRTY)) for r in page_refs]
    probes_ref = state.refs.get("probe_exchanges")
    return ObservationBundle(
        pages=pages,
        endpoints=_endpoints(project, _ref(state, "endpoints")),
        probe_exchanges=_exchanges(project, probes_ref) if probes_ref else [],
        docs=[],
    )


def run_spec(project: Project, gateway: Gateway) -> None:
    """Analyst + critic turn the observation bundle into a behavior spec (dirty zone)."""
    state = _require(project, Phase.SPEC)
    card = project.card
    spec = build_spec(
        gateway, _bundle(project, state), product_name=card.product_name, policy=card.data_policy
    )
    ref = project.store.put_json(Zone.DIRTY, "spec", "spec", spec.model_dump(mode="json"))
    _complete(project, Phase.SPEC, {"spec": ref.id})


# --- barrier ------------------------------------------------------------------------------


def _scenarios(project: Project, ref: str, reader: Zone) -> list[Scenario]:
    return [Scenario.model_validate(s) for s in project.store.get_json(ref, reader)]


def release_draft_path(project: Project) -> Path:
    """Where `run_prepare_release` writes the markdown for human review."""
    return project.dir / RELEASE_DRAFT_MD


def _draft(project: Project) -> PreparedRelease:
    state = load_state(project)
    return PreparedRelease.model_validate(
        project.store.get_json(_ref(state, "release_draft"), Zone.DIRTY)
    )


def draft_sha256(project: Project) -> str:
    """Package SHA-256 (spec + scenarios) of the current release draft: what an approver signs."""
    return _draft(project).package_sha256


def run_prepare_release(project: Project) -> None:
    """Sanitize spec + scenarios into a draft and write its markdown for the approver."""
    state = _require(project, Phase.PREPARE_RELEASE)
    spec = BehaviorSpec.model_validate(project.store.get_json(_ref(state, "spec"), Zone.DIRTY))
    scenarios = _scenarios(project, _ref(state, "scenarios"), Zone.DIRTY)
    draft_ref = prepare_release(project, spec, scenarios)
    md_ref = _markdown_ref(project, draft_ref.id)
    release_draft_path(project).write_bytes(project.store.get(md_ref, Zone.DIRTY))
    _complete(
        project,
        Phase.PREPARE_RELEASE,
        {"release_draft": draft_ref.id, "release_draft_md": md_ref},
    )


def _markdown_ref(project: Project, draft_ref: str) -> str:
    """The review markdown of `draft_ref`, from the `barrier.prepared` event just appended.

    (Several markdown artifacts can share a name: same spec, different scenarios/findings.)
    """
    for event in reversed(project.ledger.events()):
        if event.type == "barrier.prepared" and event.payload.get("draft_ref") == draft_ref:
            return str(event.payload["markdown_ref"])
    raise RuntimeError(f"no barrier.prepared event for draft {draft_ref}")


def run_release(project: Project, approval: Approval) -> None:
    """Release exactly the approved draft into the RELEASED zone."""
    state = _require(project, Phase.RELEASE)
    ref = release(project, _ref(state, "release_draft"), approval)
    _complete(project, Phase.RELEASE, {"release": ref.id})


# --- clean zone, parity, audit ------------------------------------------------------------


def run_implement(
    project: Project, gateway: Gateway, sandbox: Sandbox, *, feedback: Sequence[str] = ()
) -> ImplementResult:
    """Implement the released package in `sandbox.workdir` (clean zone)."""
    state = _require(project, Phase.IMPLEMENT)
    result = implement(
        project,
        _ref(state, "release"),
        gateway,
        sandbox,
        ImplementConfig(feedback=list(feedback)),
    )
    refs = {"code": result.code_ref} if result.code_ref else {}
    _complete(project, Phase.IMPLEMENT, refs)
    return result


def released_scenarios_write(project: Project) -> bool:
    """True when a released scenario has a step other than GET/HEAD (False before release)."""
    state = load_state(project)
    if "release" not in state.refs:
        return False
    return any(
        step.step.method.upper() not in ("GET", "HEAD")
        for scenario in _released_scenarios(project, state)
        for step in scenario.steps
    )


def _released_scenarios(project: Project, state: PipelineState) -> list[Scenario]:
    package = project.store.get_json(_ref(state, "release"), Zone.VERIFIER)
    return [Scenario.model_validate(s) for s in package["scenarios"]]


def run_parity_phase(
    project: Project,
    clone_url: str,
    *,
    reset_original: Callable[[], None] | None = None,
    reset_clone: Callable[[], None] | None = None,
    delay_s: float = _DEFAULT_DELAY_S,
) -> ParityReport:
    """Differential run: the full (dirty) scenarios on the original, their released projections
    (what the clean zone was given) on the clone.

    Requests to the original start at least `delay_s` apart. Unless the card marks the target
    as a sandbox, scenarios that would write to it (any non-GET/HEAD step) are skipped and
    reported as `skipped_unsafe`.
    """
    state = _require(project, Phase.PARITY)
    scenarios = _scenarios(project, _ref(state, "scenarios"), Zone.VERIFIER)
    report = run_parity(
        scenarios,
        _origin(project.card.target_base_url),
        clone_url,
        reset_original=reset_original,
        reset_clone=reset_clone,
        released=_released_scenarios(project, state),
        read_only_original=not project.card.target_is_sandbox,
        original_delay_s=delay_s,
    )
    ref = project.store.put_json(
        Zone.VERIFIER, "parity_report", "parity_report", report.model_dump(mode="json")
    )
    _complete(project, Phase.PARITY, {"parity_report": ref.id})
    return report


def _clone_cmd(port: int) -> list[str]:
    return ["python", "-m", "uvicorn", _CLONE_MODULE, "--port", str(port), "--host", "127.0.0.1"]


class CloneService:
    """The clone (`main:app` in the sandbox workdir) on a fixed port; `restart` resets its state.

    Raises RuntimeError when the service does not start.
    """

    def __init__(self, sandbox: Sandbox, port: int) -> None:
        self._sandbox = sandbox
        self._port = port
        self._handle = self._start()

    @property
    def base_url(self) -> str:
        return self._handle.base_url

    def _start(self) -> ServiceHandle:
        try:
            return self._sandbox.start(_clone_cmd(self._port), port=self._port)
        except (RuntimeError, TimeoutError) as exc:
            raise RuntimeError(f"clone service did not start: {exc}") from exc

    def restart(self) -> None:
        self._handle.stop()
        self._handle = self._start()

    def stop(self) -> None:
        self._handle.stop()


def run_build_loop(
    project: Project,
    gateway: Gateway,
    sandbox_factory: Callable[[], Sandbox],
    *,
    max_rounds: int = 3,
    reset_original: Callable[[], None] | None = None,
    delay_s: float = _DEFAULT_DELAY_S,
) -> ParityReport:
    """implement → start the clone → parity → sanitized feedback → implement again.

    `sandbox_factory` is called once per round. The workspace is meant to carry over between
    rounds (the template only fills missing files), so the factory should return a sandbox on
    the same workdir every time. The clone is reset by restarting it on the same port.
    `delay_s` is the pause between requests to the original during parity.
    """
    _require(project, Phase.IMPLEMENT)
    card = project.card
    feedback: list[str] = []
    report: ParityReport | None = None
    start_error: str | None = None
    for round_no in range(1, max_rounds + 1):
        sandbox = sandbox_factory()
        run_implement(project, gateway, sandbox, feedback=feedback)
        report = None
        try:
            clone = CloneService(sandbox, free_port())
        except RuntimeError as exc:
            start_error = str(exc)
        else:
            start_error = None
            try:
                report = run_parity_phase(
                    project,
                    clone.base_url,
                    reset_original=reset_original,
                    reset_clone=clone.restart,
                    delay_s=delay_s,
                )
            finally:
                clone.stop()

        state = load_state(project)
        state.parity_rounds += 1
        save_state(project, state)
        met = report is not None and meets_threshold(report)
        project.ledger.append(
            "pipeline.build_round",
            Zone.VERIFIER.value,
            _ACTOR,
            {
                "round": round_no,
                "service_started": report is not None,
                "ratio": report.ratio if report is not None else 0.0,
                "critical_ratio": report.critical_ratio if report is not None else 0.0,
                "meets_threshold": met,
            },
        )
        if met or round_no == max_rounds:
            break
        if report is None:
            # The start error holds the clone's own log tail; the clean zone gets a fixed line.
            feedback = [CLONE_DID_NOT_START]
            continue
        feedback = feedback_for_clean_zone(
            report,
            _released_scenarios(project, state),
            expression_index(project),
            brand_terms=card.brand_terms,
            product_name=card.product_name,
            target_domains=target_domains(project),
            ledger=project.ledger,
        )
    if report is None:
        if start_error is not None:
            raise RuntimeError(start_error)
        raise RuntimeError("max_rounds must be at least 1")
    return report


def _code_files(project: Project, ref: str) -> dict[str, str]:
    files: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(project.store.get(ref, Zone.VERIFIER))) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            try:
                files[info.filename] = archive.read(info).decode("utf-8")
            except UnicodeDecodeError:
                continue
    return files


def _expression_texts(project: Project) -> list[str]:
    """The original's JS/CSS/WASM (`expression` artifacts); HTML documents are not included."""
    store = project.store
    return [
        store.get(ref.id, Zone.VERIFIER).decode("utf-8", errors="replace")
        for ref in store.list(Zone.DIRTY, "expression")
    ]


@dataclass(frozen=True)
class AuditResult:
    zip_path: Path
    similarity: SimilarityReport
    brand_hits: list[str]

    @property
    def passed(self) -> bool:
        """Similarity under the threshold and no brand term in the clone's code."""
        return self.similarity.ok and not self.brand_hits


def run_audit(project: Project, out_dir: Path) -> AuditResult:
    """Code similarity, brand mentions and the evidence pack.

    The phase completes whatever the findings; callers decide what a failed audit means.
    """
    state = _require(project, Phase.AUDIT)
    code = _code_files(project, _ref(state, "code"))
    similarity = code_similarity(code, _expression_texts(project))
    brand_hits = brand_mentions(code, project.card.brand_terms)
    parity = ParityReport.model_validate(
        project.store.get_json(_ref(state, "parity_report"), Zone.VERIFIER)
    )
    zip_path = build_evidence_pack(
        project,
        parity=parity,
        similarity=similarity,
        brand_hits=brand_hits,
        out_dir=Path(out_dir),
    )
    _complete(project, Phase.AUDIT, {})
    return AuditResult(zip_path=zip_path, similarity=similarity, brand_hits=brand_hits)


# --- gateway ------------------------------------------------------------------------------


def build_gateway(
    project: Project, settings: Settings | None = None, env: Mapping[str, str] = os.environ
) -> Gateway:
    """Gateway over the providers whose keys are in `env`, logging to the project ledger."""
    settings = settings if settings is not None else load_settings()
    return Gateway(
        settings,
        build_providers(settings, env),
        project.ledger,
        transcripts_dir=project.dir / "transcripts",
    )


__all__ = [
    "CLONE_DID_NOT_START",
    "PHASE_REFS",
    "PREREQUISITES",
    "RELEASE_DRAFT_MD",
    "WORKSPACES_DIR",
    "AuditResult",
    "CloneService",
    "Phase",
    "PhaseOrderError",
    "PipelineState",
    "build_gateway",
    "draft_sha256",
    "load_state",
    "record_observation",
    "release_draft_path",
    "released_scenarios_write",
    "run_audit",
    "run_build_loop",
    "run_implement",
    "run_observe",
    "run_oracle",
    "run_parity_phase",
    "run_prepare_release",
    "run_release",
    "run_spec",
    "save_state",
    "workspace_dir",
]
