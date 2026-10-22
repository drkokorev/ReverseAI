"""User-facing messages shared by the CLI and the web console.

Both front ends report the same failures with the same words: a phase label, a prefix per
error class, and the error's own detail. The text comes from the i18n catalogs.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from playwright.sync_api import Error as PlaywrightError
from pydantic import ValidationError

from reverseai.barrier.release import ReleaseError
from reverseai.i18n import Labels, t
from reverseai.llm.gateway import GatewayError
from reverseai.llm.jsonout import LLMOutputError
from reverseai.llm.policy import PolicyViolation
from reverseai.parity.differential import ParityReport
from reverseai.pipeline import Phase, PhaseOrderError
from reverseai.project import IntakeError

PHASE_LABELS: Labels[Phase] = Labels("phase", list(Phase))

_ERROR_LABELS: list[tuple[type[BaseException], str]] = [
    (IntakeError, "error.intake"),
    (ReleaseError, "error.release"),
    (PolicyViolation, "error.policy"),
    (GatewayError, "error.gateway"),
    (LLMOutputError, "error.llm_output"),
    (yaml.YAMLError, "error.yaml"),
]

# Expected failures: reported as one line, never as a traceback.
USER_ERRORS: tuple[type[BaseException], ...] = (
    RuntimeError, IntakeError, ReleaseError, ValidationError, PolicyViolation, GatewayError,
    LLMOutputError, yaml.YAMLError,
)  # fmt: skip
# Failures of the machine rather than of the input (files, browser).
ENVIRONMENT_ERRORS: tuple[type[BaseException], ...] = (OSError, PlaywrightError)


class PlainError(RuntimeError):
    """A user error whose message is already translated; reported as is."""


# pydantic error types with their own wording; anything else is "invalid value".
_VALIDATION_TYPES: dict[str, str] = {
    "extra_forbidden": "extra_forbidden",
    "missing": "missing",
    "json_invalid": "json_invalid",
    "json_type": "json_invalid",
    "string_type": "string_type",
    "string_too_short": "string_too_short",
    "bool_type": "bool_type",
    "bool_parsing": "bool_type",
    "int_type": "int_type",
    "int_parsing": "int_type",
    "float_type": "float_type",
    "float_parsing": "float_type",
    "list_type": "list_type",
    "dict_type": "dict_type",
    "model_type": "dict_type",
}
_VALIDATION_SHOWN = 3


def validation_summary(exc: ValidationError) -> str:
    """The first errors of `exc` as one line: "field — what is wrong; …; and N more".

    pydantic's own text is multi-line English with documentation URLs; it is never shown.
    """
    errors = exc.errors(include_url=False, include_input=False, include_context=False)
    parts = []
    for error in errors[:_VALIDATION_SHOWN]:
        where = ".".join(str(part) for part in error["loc"])
        label = t("validation." + _VALIDATION_TYPES.get(error["type"], "invalid"))
        parts.append(f"{where} — {label}" if where else label)
    if len(errors) > _VALIDATION_SHOWN:
        parts.append(t("validation.more", count=len(errors) - _VALIDATION_SHOWN))
    return "; ".join(parts)


def user_message(exc: BaseException) -> str:
    """The description of an expected failure (without the leading "Error:")."""
    if isinstance(exc, PhaseOrderError):
        return t("error.phase_order", label=PHASE_LABELS[exc.missing], phase=exc.missing.value)
    if isinstance(exc, PlainError):
        return str(exc)
    if isinstance(exc, ValidationError):
        return t("error.validation", title=exc.title, summary=validation_summary(exc))
    for cls, key in _ERROR_LABELS:
        if isinstance(exc, cls):
            return f"{t(key)}: {exc}"
    return str(exc)


def build_summary(report: ParityReport, workdir: Path) -> list[str]:
    """The lines `build` prints after the loop (the console's build job logs the same)."""
    lines = [
        t(
            "build.parity_line",
            passed=report.passed, total=report.total, ratio=report.ratio,
            critical_passed=report.critical_passed, critical_total=report.critical_total,
            critical_ratio=report.critical_ratio, unstable=len(report.unstable),
        )
    ]
    if report.skipped_unsafe:
        lines.append(t("build.skipped_unsafe", count=len(report.skipped_unsafe)))
    lines.append(t("build.withheld_mismatches", count=report.withheld_mismatches))
    lines.append(t("build.workdir", path=workdir))
    return lines


__all__ = [
    "ENVIRONMENT_ERRORS",
    "PHASE_LABELS",
    "USER_ERRORS",
    "PlainError",
    "build_summary",
    "user_message",
    "validation_summary",
]
