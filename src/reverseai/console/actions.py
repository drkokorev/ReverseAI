"""Pipeline actions as the console runs them: the same calls and lines as the CLI commands.

Each `*_job` returns an `Action` for the job runner; it logs what the CLI prints and returns a
message when the CLI would exit with code 2 (threshold missed, audit failed). `locked` runs an
action under the project lock (D-015), as the CLI runs its commands. `approve` is synchronous:
it re-checks and releases the draft under the same lock.
"""

from __future__ import annotations

import datetime as dt

from reverseai import pipeline
from reverseai.barrier.release import Approval, ReleaseError
from reverseai.console.context import GatewayFactory, SandboxFactory
from reverseai.console.evidence import evidence_dir
from reverseai.console.jobs import Action, JobLog
from reverseai.console.roles import approval_role
from reverseai.i18n import t
from reverseai.messages import PHASE_LABELS, PlainError, build_summary
from reverseai.parity.differential import meets_threshold
from reverseai.pipeline import Phase
from reverseai.project import Project, project_lock

# URL action -> the phase whose prerequisite gates it (and whose label names the job).
RUNNABLE: dict[str, Phase] = {
    "observe": Phase.OBSERVE,
    "oracle": Phase.ORACLE,
    "spec": Phase.SPEC,
    "prepare-release": Phase.PREPARE_RELEASE,
    "build": Phase.IMPLEMENT,
    "audit": Phase.AUDIT,
}


def action_label(action: str) -> str:
    return t("console.build_label") if action == "build" else PHASE_LABELS[RUNNABLE[action]]


def done_line(phase: Phase) -> str:
    return t("phase_done", label=PHASE_LABELS[phase], phase=phase.value)


def ensure_free(project: Project) -> None:
    """Raise `ProjectBusy` now if another process holds the project (before a job starts).

    Only a courtesy check: the job itself takes the lock (see `locked`), which is what counts.
    """
    with project_lock(project.dir):
        pass


def locked(project: Project, work: Action) -> Action:
    """`work` with the project lock held for its whole run; busy → the job fails with a message."""

    def run(log: JobLog) -> str | None:
        with project_lock(project.dir):
            return work(log)

    return run


def observe_job(project: Project, *, max_pages: int, submit_forms: bool, probe: bool) -> Action:
    def work(log: JobLog) -> None:
        pipeline.run_observe(project, max_pages=max_pages, submit_forms=submit_forms, probe=probe)
        log(done_line(Phase.OBSERVE))

    return work


def oracle_job(project: Project) -> Action:
    def work(log: JobLog) -> None:
        pipeline.run_oracle(project)
        log(done_line(Phase.ORACLE))

    return work


def spec_job(project: Project, gateway_factory: GatewayFactory) -> Action:
    def work(log: JobLog) -> None:
        pipeline.run_spec(project, gateway_factory(project))
        log(done_line(Phase.SPEC))

    return work


def prepare_release_job(project: Project) -> Action:
    def work(log: JobLog) -> None:
        pipeline.run_prepare_release(project)
        sha = pipeline.draft_sha256(project)
        draft_file = pipeline.release_draft_path(project)
        log(t("release.draft_for_review", path=f"{project.dir.name}/{draft_file.name}"))
        log(t("release.package_sha", sha=sha))
        log(done_line(Phase.PREPARE_RELEASE))
        log(t("console.prepare_release.next"))

    return work


def build_job(
    project: Project,
    gateway_factory: GatewayFactory,
    sandbox_factory: SandboxFactory,
    *,
    max_rounds: int,
    allow_unstable: bool,
) -> Action:
    def work(log: JobLog) -> str | None:
        unstable = pipeline.released_scenarios_write(project)
        if project.card.target_is_sandbox and not allow_unstable and unstable:
            raise PlainError(t("console.build.unstable_refused"))
        workdir = pipeline.workspace_dir(project)
        if not getattr(sandbox_factory(workdir), "isolated", False):
            log(t("build.local_sandbox_warning"))
        report = pipeline.run_build_loop(
            project,
            gateway_factory(project),
            lambda: sandbox_factory(workdir),
            max_rounds=max_rounds,
        )
        for line in build_summary(report, workdir):
            log(line)
        if meets_threshold(report):
            log(t("build.threshold_met"))
            return None
        log(t("build.threshold_missed"))
        return t("build.threshold_missed")

    return work


def audit_job(project: Project) -> Action:
    def work(log: JobLog) -> str | None:
        result = pipeline.run_audit(project, evidence_dir(project))
        log(t("audit.pack", path=result.zip_path))
        log(done_line(Phase.AUDIT))
        similarity = result.similarity
        log(t("audit.similarity", score=similarity.max_score, threshold=similarity.threshold))
        log(t("audit.brand_hits", count=len(result.brand_hits)))
        if result.passed:
            return None
        log(t("audit.failed"))
        return t("audit.failed")

    return work


def approve(project: Project, *, approver: str, role: str, sha: str) -> None:
    """Release the current draft with the approval of `approver` (as `reverseai approve`).

    The check (not released yet, the hash matches the current draft) and the release run under
    the project lock, so no other command can replace the draft in between.
    """
    with project_lock(project.dir):
        if Phase.RELEASE in pipeline.load_state(project).completed:
            raise PlainError(t("console.already_released"))
        approval = Approval(
            approver=approver,
            role=approval_role(role),
            approved_at=dt.datetime.now(dt.UTC).isoformat(),
            package_sha256=sha,
        )
        try:
            pipeline.run_release(project, approval)  # logs barrier.rejected on a mismatch
        except ReleaseError:
            if sha != pipeline.draft_sha256(project):  # the page showed an older draft
                raise PlainError(t("console.draft_changed")) from None
            raise
