"""Barrier release: sanitized draft for human review, then release of exactly what was approved."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from reverseai.barrier.sanitizer import (
    WARNING_KINDS,
    ExpressionIndex,
    Finding,
    SanitizeReport,
    blocking,
    build_expression_index,
    key_renames,
    mask_identity,
    sanitize_scenarios,
    sanitize_spec,
    withheld_expectations,
)
from reverseai.i18n import has, t
from reverseai.observe.har import parse_har
from reverseai.oracle.model import Scenario
from reverseai.project import Project
from reverseai.spec.model import BehaviorSpec
from reverseai.spec.render import render_markdown
from reverseai.zones.store import ArtifactRef, Zone

_ACTOR = "barrier"
_RAW_KINDS = ("expression", "document")
_PAGE_FIELDS = ("title", "text_excerpt")


class ReleaseError(Exception):
    """The draft may not cross the barrier (approval mismatch or the draft is not clean).

    `key` names the refusal (catalog entry `release_error.<key>`); the message is in the active
    language, `reason` (what the ledger records) is always English. Any other text is taken
    as the message itself.
    """

    def __init__(self, key: str, **params: object) -> None:
        entry = f"release_error.{key}"
        message = t(entry, **params) if has(entry) else key
        super().__init__(message)
        self.key = key
        self.reason = t(entry, lang="en", **params) if has(entry) else key


class PreparedRelease(BaseModel):
    spec: BehaviorSpec
    scenarios: list[Scenario]
    report: SanitizeReport
    spec_sha256: str
    package_sha256: str  # what an approval binds: spec and scenarios, as released


class Approval(BaseModel):
    approver: str = Field(min_length=1)  # who signs: never blank in the ledger
    role: Literal["operator", "customer_analyst"]
    approved_at: str
    package_sha256: str

    @field_validator("approver", mode="before")
    @classmethod
    def _strip_approver(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def package_sha256(spec: BehaviorSpec, scenarios: list[Scenario]) -> str:
    """SHA-256 hex of the canonical JSON of ``{spec, scenarios}`` (exactly what is released)."""
    canonical = json.dumps(
        {
            "spec": spec.model_dump(mode="json"),
            "scenarios": [s.model_dump(mode="json") for s in scenarios],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strings(value: Any) -> Iterator[str]:
    """Every string value inside a JSON document (dict keys are not included)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _page_texts(page: dict) -> list[str]:
    labels = [
        str(field.get("label") or "")
        for form in page.get("forms") or []
        for field in form.get("fields") or []
    ]
    return [
        *(str(page.get(name) or "") for name in _PAGE_FIELDS),
        " ".join(str(b) for b in page.get("buttons") or []),
        " ".join(label for label in labels if label),
    ]


def _expression_index(project: Project) -> ExpressionIndex:
    """Index of everything the dirty zone saw of the original's expression.

    Index texts get the same domain/brand masking as sanitized prose, so copy surrounding a
    brand name or URL still matches after the prose itself was masked.
    """
    store = project.store
    card = project.card
    texts: list[str] = []
    for kind in _RAW_KINDS:
        for ref in store.list(Zone.DIRTY, kind):
            texts.append(store.get(ref.id, Zone.DIRTY).decode("utf-8", errors="replace"))
    for ref in store.list(Zone.DIRTY, "page"):
        texts += _page_texts(store.get_json(ref.id, Zone.DIRTY))
    for ref in store.list(Zone.DIRTY, "har"):
        parsed = parse_har(store.get_json(ref.id, Zone.DIRTY), card.allowed_domains)
        for exchange in parsed.exchanges:
            texts += _strings(exchange.response_json)
    for ref in store.list(Zone.DIRTY, "exchanges"):  # pipeline: HAR + probe exchanges
        for exchange in store.get_json(ref.id, Zone.DIRTY):
            if isinstance(exchange, dict):
                texts += _strings(exchange.get("response_json"))
    domains = _target_domains(project)
    return build_expression_index(
        mask_identity(
            text,
            brand_terms=card.brand_terms,
            product_name=card.product_name,
            target_domains=domains,
        )
        for text in texts
    )


def expression_index(project: Project) -> ExpressionIndex:
    """Public entry to the barrier's index of the original's expression (e.g. parity feedback)."""
    return _expression_index(project)


def target_domains(project: Project) -> list[str]:
    """The card's allowed domains plus the target host, as the barrier masks them."""
    return _target_domains(project)


def _target_domains(project: Project) -> list[str]:
    card = project.card
    domains = list(card.allowed_domains)
    host = urlparse(card.target_base_url).hostname
    if host and host.lower() not in {d.lower() for d in domains}:
        domains.append(host)
    return domains


def _sanitize(
    project: Project, spec: BehaviorSpec, scenarios: list[Scenario]
) -> tuple[BehaviorSpec, list[Scenario], list[Finding]]:
    index = _expression_index(project)
    domains = _target_domains(project)
    brands = project.card.brand_terms
    # One rename per JSON key for the whole package: spec and scenarios agree on every name.
    renames = key_renames(
        spec, scenarios, brand_terms=brands, product_name=spec.product_name,
        target_domains=domains,
    )
    clean_spec, report = sanitize_spec(
        spec, index, brand_terms=brands, target_domains=domains, renames=renames
    )
    clean_scenarios, scenario_findings = sanitize_scenarios(
        scenarios,
        index,
        brand_terms=brands,
        product_name=clean_spec.product_name,
        target_domains=domains,
        renames=renames,
    )
    return clean_spec, clean_scenarios, report.findings + scenario_findings


def _check_product_name(project: Project, spec: BehaviorSpec) -> None:
    if spec.product_name != project.card.product_name:
        raise ReleaseError(
            "product_name", spec=repr(spec.product_name), card=repr(project.card.product_name)
        )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _scenario_lines(scenario: Scenario) -> list[str]:
    critical = f" ({t('release_md.critical')})" if scenario.critical else ""
    lines = [f"### {scenario.id}: {scenario.title}{critical}", ""]
    for n, scenario_step in enumerate(scenario.steps, start=1):
        step, expect = scenario_step.step, scenario_step.expect
        body = ""
        if step.json_body is not None:
            body = f" {t('release_md.body')}: `{_json(step.json_body)}`"
        status = t("release_md.status", status=expect.status)
        lines.append(f"{n}. `{step.method} {step.path}`{body} → {status}")
        if expect.json_shape:
            lines.append(f"   - {t('release_md.shape')}: `{_json(expect.json_shape)}`")
        for pointer, value in expect.json_equals.items():
            lines.append(f"   - `{pointer}` = {_json(value)}")
        if step.save:
            lines.append(f"   - {t('release_md.save')}: `{_json(step.save)}`")
    lines.append("")
    return lines


def _review_markdown(draft: PreparedRelease, withheld: list[tuple[str, int, str]]) -> str:
    """What the approver signs: the spec, every released scenario, what was withheld."""
    lines = [render_markdown(draft.spec), "## " + t("release_md.scenarios"), ""]
    for scenario in draft.scenarios:
        lines += _scenario_lines(scenario)
    if not draft.scenarios:
        lines += ["—", ""]
    lines += ["## " + t("release_md.withheld"), ""]
    lines += [
        "- " + t("release_md.withheld_row", scenario=sid, step=step + 1, pointer=pointer)
        for sid, step, pointer in withheld
    ]
    lines += [""] if withheld else ["—", ""]
    warnings = [f for f in draft.report.findings if f.kind in WARNING_KINDS]
    if warnings:
        lines += ["## " + t("release_md.warnings"), ""]
        lines.append(t("release.body_warning_note"))
        lines.append("")
        lines += [f"- {f.location}: {f.excerpt!r}" for f in warnings]
        lines.append("")
    lines += ["## " + t("release_md.report"), ""]
    lines.append(t("release_md.package_sha", sha=draft.package_sha256))
    lines.append(t("release_md.spec_sha", sha=draft.spec_sha256))
    lines.append(t("release_md.scenario_count", count=len(draft.scenarios)))
    lines.append("")
    for f in draft.report.findings:
        lines.append(f"- {t('finding.' + f.kind)} — {f.location}: {f.excerpt!r}")
    if not draft.report.findings:
        lines.append("—")
    return "\n".join(lines) + "\n"


def prepare_release(
    project: Project, spec: BehaviorSpec, scenarios: list[Scenario]
) -> ArtifactRef:
    """Sanitize the spec and scenarios and store the draft (plus markdown) for human review."""
    _check_product_name(project, spec)
    clean_spec, clean_scenarios, findings = _sanitize(project, spec, scenarios)
    draft = PreparedRelease(
        spec=clean_spec,
        scenarios=clean_scenarios,
        report=SanitizeReport(findings=findings),
        spec_sha256=clean_spec.sha256(),
        package_sha256=package_sha256(clean_spec, clean_scenarios),
    )
    store = project.store
    ref = store.put_json(
        Zone.DIRTY, "release_draft", f"release_draft:{draft.package_sha256}",
        draft.model_dump(mode="json"),
    )
    withheld = [
        (before.id, step, pointer)
        for before, after in zip(scenarios, clean_scenarios, strict=True)
        for step, pointer in withheld_expectations(before, after)
    ]
    md_ref = store.put(
        Zone.DIRTY, "release_draft_md", f"release_draft:{draft.package_sha256}.md",
        _review_markdown(draft, withheld).encode("utf-8"),
    )
    project.ledger.append(
        "barrier.prepared",
        Zone.DIRTY.value,
        _ACTOR,
        {
            "draft_ref": ref.id,
            "markdown_ref": md_ref.id,
            "spec_sha256": draft.spec_sha256,
            "package_sha256": draft.package_sha256,
            "scenarios": len(clean_scenarios),
            "findings": len(findings),
        },
    )
    return ref


def _load_draft(project: Project, draft_ref: str) -> PreparedRelease:
    try:
        ref = project.store.ref(draft_ref, Zone.DIRTY)
    except KeyError:
        raise ReleaseError("no_artifact", ref=draft_ref) from None
    try:
        project.store.ref(draft_ref, Zone.DIRTY, kind="release_draft")
    except KeyError:
        raise ReleaseError("not_a_draft", ref=draft_ref, kind=repr(ref.kind)) from None
    try:
        return PreparedRelease.model_validate(project.store.get_json(draft_ref, Zone.DIRTY))
    except ValueError as exc:  # integrity failure, bad JSON/UTF-8, schema validation
        raise ReleaseError("malformed", ref=draft_ref, detail=exc) from exc


def _check(project: Project, draft: PreparedRelease, approval: Approval) -> None:
    if approval.package_sha256 != draft.package_sha256:
        raise ReleaseError("approval_mismatch")
    if package_sha256(draft.spec, draft.scenarios) != draft.package_sha256:
        raise ReleaseError("package_mismatch")
    if draft.spec.sha256() != draft.spec_sha256:
        raise ReleaseError("spec_mismatch")
    _check_product_name(project, draft.spec)
    _, scenarios, findings = _sanitize(project, draft.spec, draft.scenarios)
    findings = blocking(findings)  # body warnings were shown to the approver; they never block
    if findings:
        where = ", ".join(sorted({f"{f.kind}@{f.location}" for f in findings}))
        raise ReleaseError("not_clean", where=where)
    if scenarios != draft.scenarios:
        raise ReleaseError("would_drop")


def release(project: Project, draft_ref: str, approval: Approval) -> ArtifactRef:
    """Release exactly the approved draft into the RELEASED zone, after a fresh re-check."""
    try:
        draft = _load_draft(project, draft_ref)
        _check(project, draft, approval)
    except ReleaseError as exc:
        project.ledger.append(
            "barrier.rejected",
            Zone.DIRTY.value,
            _ACTOR,
            {
                "draft_ref": draft_ref,
                "package_sha256": approval.package_sha256,
                "reason": exc.reason,
            },
        )
        raise
    # Excerpts quote the original and stay in the dirty-zone draft; only kind/location cross.
    redacted = SanitizeReport(
        findings=[f.model_copy(update={"excerpt": ""}) for f in draft.report.findings]
    )
    package = {
        "spec": draft.spec.model_dump(mode="json"),
        "scenarios": [s.model_dump(mode="json") for s in draft.scenarios],
        "approval": approval.model_dump(mode="json"),
        "sanitize_report": redacted.model_dump(mode="json"),
    }
    ref = project.store.put_json(
        Zone.RELEASED, "release_package", f"release:{draft.package_sha256}", package
    )
    project.ledger.append(
        "barrier.approved", Zone.RELEASED.value, _ACTOR, approval.model_dump(mode="json")
    )
    project.ledger.append(
        "barrier.release",
        Zone.RELEASED.value,
        _ACTOR,
        {
            "ref": ref.id,
            "spec_sha256": draft.spec_sha256,
            "package_sha256": draft.package_sha256,
            "scenarios": len(draft.scenarios),
        },
    )
    return ref
