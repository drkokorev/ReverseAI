"""Feedback for the clean zone: what failed, never what the original answered.

A line states the failing scenario, step and the *expected* behavior only. Expected values are
included only when the barrier's `releasable_value` rule allows them; paths and pointers are
identifiers and follow the barrier's identifier rule (`mask_identifier`, D-008), the same rule
that released them. Titles are the released ones. The clone's/original's `actual` values and
anything else from raw responses never appear.
"""

from __future__ import annotations

import hashlib
from typing import Any

from reverseai.barrier.sanitizer import (
    ExpressionIndex,
    mask_identifier,
    releasable_value,
    request_values,
    sanitize_text,
)
from reverseai.oracle.model import Scenario, StepFailure
from reverseai.parity.differential import ParityReport
from reverseai.provenance.ledger import Ledger

MAX_FEEDBACK_LINES = 30
VALUE_WITHHELD = "(value withheld)"


def feedback_for_clean_zone(
    report: ParityReport,
    scenarios: list[Scenario],
    index: ExpressionIndex,
    *,
    brand_terms: list[str],
    product_name: str,
    target_domains: list[str],
    ledger: Ledger | None = None,
) -> list[str]:
    """One sanitized line per scenario that passed on the original but failed on the clone.

    `scenarios` are the released ones (what the clean zone was given).
    """
    by_id = {s.id: s for s in scenarios}

    def identifier(text: str, *, url_path: bool = False) -> str:
        return mask_identifier(
            text,
            location="parity.feedback",
            brand_terms=brand_terms,
            product_name=product_name,
            target_domains=target_domains,
            url_path=url_path,
        )[0]

    def check(text: str) -> tuple[str, bool]:
        clean, findings = sanitize_text(
            text,
            location="parity.feedback",
            index=index,
            brand_terms=brand_terms,
            product_name=product_name,
            target_domains=target_domains,
        )
        return clean, not findings

    def releasable(value: Any, sent: set[str]) -> bool:
        return releasable_value(
            value,
            request_values=sent,
            index=index,
            brand_terms=brand_terms,
            product_name=product_name,
            target_domains=target_domains,
        )

    def expectation(failure: StepFailure, sent: set[str]) -> str:
        if failure.kind == "status" and isinstance(failure.expected, int):
            return f"expected status = {failure.expected}"
        pointer = "" if failure.pointer is None else " " + identifier(failure.pointer)
        value = str(failure.expected) if releasable(failure.expected, sent) else VALUE_WITHHELD
        return f"expected {failure.kind}{pointer} = {value}"

    lines: list[str] = []
    # critical failures first, so the line cap never hides them (sort is stable)
    for result in sorted(report.results, key=lambda r: not r.critical):
        if not result.original_ok or result.clone_ok or not result.failures:
            continue
        if len(lines) == MAX_FEEDBACK_LINES:
            break
        failure = result.failures[0]
        scenario = by_id.get(result.id)
        sent = request_values(scenario) if scenario is not None else set()
        title = scenario.title if scenario is not None else result.title
        title = check(title)[0]
        step_no = failure.step + 1
        where = f"step {step_no}"
        if scenario is not None and 0 <= failure.step < len(scenario.steps):
            step = scenario.steps[failure.step].step
            where = f"step {step_no} {step.method} {identifier(step.path, url_path=True)}"
        lines.append(f"{title}: {where}: {expectation(failure, sent)}")

    if ledger is not None:
        ledger.append(
            "parity.feedback",
            "verifier",
            "parity",
            {"lines": len(lines), "sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest()},
        )
    return lines
