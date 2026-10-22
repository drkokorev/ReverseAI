"""Differential run of the same scenarios against the original and the clone.

Parity is measured on HTTP behavior and data only. Scenarios that already fail on the original
are `unstable` (non-deterministic or environment dependent) and are excluded from all totals.
With `read_only_original`, scenarios that would send anything but GET/HEAD to the original are
not run at all (`skipped_unsafe`, excluded from all totals). The original is checked with the full (dirty) scenario; the clone is checked against the
released projection of it (sanitized paths and bodies, withheld expected values removed), so it
is never required to produce values the clean zone never saw. Mismatches on withheld values are
only counted (`withheld_mismatches`). This module runs on the dirty side: its report may hold
raw values from the original.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from reverseai.barrier.sanitizer import withheld_expectations
from reverseai.oracle.model import Scenario, StepFailure
from reverseai.oracle.runner import run_scenarios


class ScenarioParity(BaseModel):
    """Outcome of one scenario.

    Unstable scenarios (failed on the original) are reported with ``original_ok=False`` and
    ``clone_ok=False``; they were not run against the clone.
    """

    id: str
    title: str
    critical: bool
    original_ok: bool
    clone_ok: bool
    failures: list[StepFailure]


class ParityReport(BaseModel):
    total: int
    passed: int
    critical_total: int
    critical_passed: int
    unstable: list[str]
    results: list[ScenarioParity]
    withheld_mismatches: int = 0  # clone mismatches on values withheld by the barrier (info)
    skipped_unsafe: list[str] = []  # not run: they write and the original is not a sandbox

    @property
    def ratio(self) -> float:
        return self.passed / self.total if self.total else 1.0

    @property
    def critical_ratio(self) -> float:
        return self.critical_passed / self.critical_total if self.critical_total else 1.0


def run_parity(
    scenarios: list[Scenario],
    original_url: str,
    clone_url: str,
    *,
    reset_original: Callable[[], None] | None = None,
    reset_clone: Callable[[], None] | None = None,
    released: list[Scenario] | None = None,
    read_only_original: bool = False,
    original_delay_s: float = 0.0,
) -> ParityReport:
    """Run every scenario on the original, then the stable ones on the clone.

    `released` holds the released projections by scenario id; without it (or for an id it
    lacks) the clone is checked with the full scenario. `read_only_original` skips every
    scenario with a non-GET/HEAD step; `original_delay_s` throttles requests to the original.
    """
    skipped_unsafe = [s.id for s in scenarios if read_only_original and _writes(s)]
    scenarios = [s for s in scenarios if s.id not in skipped_unsafe]
    on_original = {
        r.id: r
        for r in run_scenarios(
            scenarios, original_url, reset=reset_original, delay_s=original_delay_s
        )
    }
    stable = [s for s in scenarios if on_original[s.id].passed]
    projections = {s.id: s for s in released or []}
    checks: list[Scenario] = []
    withheld: dict[str, set[tuple[int, str]]] = {}
    for scenario in stable:
        projection = projections.get(scenario.id, scenario)
        dropped = withheld_expectations(scenario, projection)
        withheld[scenario.id] = set(dropped)
        checks.append(_clone_check(scenario, projection, dropped))
    on_clone = {r.id: r for r in run_scenarios(checks, clone_url, reset=reset_clone)}

    results: list[ScenarioParity] = []
    unstable: list[str] = []
    passed = critical_total = critical_passed = withheld_mismatches = 0
    for scenario in scenarios:
        if scenario.id not in on_clone:
            unstable.append(scenario.id)
            results.append(
                ScenarioParity(
                    id=scenario.id,
                    title=scenario.title,
                    critical=scenario.critical,
                    original_ok=False,
                    clone_ok=False,
                    failures=[],
                )
            )
            continue
        failures = []
        for failure in on_clone[scenario.id].failures:
            if failure.kind == "value" and (failure.step, failure.pointer) in withheld[scenario.id]:
                withheld_mismatches += 1
            else:
                failures.append(failure)
        clone_ok = not failures
        passed += clone_ok
        if scenario.critical:
            critical_total += 1
            critical_passed += clone_ok
        results.append(
            ScenarioParity(
                id=scenario.id,
                title=scenario.title,
                critical=scenario.critical,
                original_ok=True,
                clone_ok=clone_ok,
                failures=failures,
            )
        )
    return ParityReport(
        total=len(scenarios) - len(unstable),
        passed=passed,
        critical_total=critical_total,
        critical_passed=critical_passed,
        unstable=unstable,
        results=results,
        withheld_mismatches=withheld_mismatches,
        skipped_unsafe=skipped_unsafe,
    )


_SAFE_METHODS = frozenset({"GET", "HEAD"})


def _writes(scenario: Scenario) -> bool:
    return any(s.step.method.upper() not in _SAFE_METHODS for s in scenario.steps)


def _clone_check(
    scenario: Scenario, projection: Scenario, withheld: list[tuple[int, str]]
) -> Scenario:
    """The released projection plus the expectations the barrier withheld.

    Released expectations (under their released, possibly renamed pointers) decide `clone_ok`;
    the withheld ones are added back only so that mismatches on them can be counted.
    """
    check = projection.model_copy(deep=True)
    for step_no, pointer in withheld:
        if step_no < len(check.steps):
            equals = check.steps[step_no].expect.json_equals
            equals.setdefault(pointer, scenario.steps[step_no].expect.json_equals[pointer])
    return check


MAX_UNSTABLE_SHARE = 0.2


def meets_threshold(
    report: ParityReport, overall: float = 0.95, critical: float = 1.0
) -> bool:
    """Whether the clone passes the parity gate.

    False when nothing was compared (total == 0), when a critical scenario is unstable, or
    when unstable scenarios exceed 20% of those run: excluding them must not make parity green.
    """
    if report.total == 0:
        return False
    if any(r.critical and not r.original_ok for r in report.results):
        return False
    if len(report.unstable) / (report.total + len(report.unstable)) > MAX_UNSTABLE_SHARE:
        return False
    return report.ratio >= overall and report.critical_ratio >= critical
