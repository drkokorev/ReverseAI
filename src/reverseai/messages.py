"""Russian user-facing messages shared by the CLI and the web console.

Both front ends report the same failures with the same words: a phase label, a Russian prefix
per error class, and the error's own detail.
"""

from __future__ import annotations

import yaml
from playwright.sync_api import Error as PlaywrightError
from pydantic import ValidationError

from reverseai.barrier.release import ReleaseError
from reverseai.llm.gateway import GatewayError
from reverseai.llm.jsonout import LLMOutputError
from reverseai.llm.policy import PolicyViolation
from reverseai.pipeline import Phase, PhaseOrderError
from reverseai.project import IntakeError

PHASE_LABELS: dict[Phase, str] = {
    Phase.INTAKE: "Приём проекта",
    Phase.OBSERVE: "Наблюдение",
    Phase.ORACLE: "Оракул поведения",
    Phase.SPEC: "Спецификация",
    Phase.PREPARE_RELEASE: "Подготовка выпуска",
    Phase.RELEASE: "Выпуск через барьер",
    Phase.IMPLEMENT: "Реализация",
    Phase.PARITY: "Проверка паритета",
    Phase.AUDIT: "Аудит",
}

_ERROR_LABELS: list[tuple[type[BaseException], str]] = [
    (IntakeError, "проверка проекта не пройдена"),
    (ReleaseError, "выпуск через барьер отклонён"),
    (PolicyViolation, "политика данных запрещает вызов модели"),
    (GatewayError, "ни одна модель не ответила"),
    (LLMOutputError, "некорректный ответ модели"),
    (yaml.YAMLError, "некорректный YAML"),
]

# Expected failures: reported as one Russian line, never as a traceback.
USER_ERRORS: tuple[type[BaseException], ...] = (
    RuntimeError, IntakeError, ReleaseError, ValidationError, PolicyViolation, GatewayError,
    LLMOutputError, yaml.YAMLError,
)  # fmt: skip
# Failures of the machine rather than of the input (files, browser).
ENVIRONMENT_ERRORS: tuple[type[BaseException], ...] = (OSError, PlaywrightError)


class PlainError(RuntimeError):
    """A user error whose message is already in Russian; reported as is."""


# pydantic error types -> Russian; anything else is «недопустимое значение».
_VALIDATION_LABELS: dict[str, str] = {
    "extra_forbidden": "неизвестное поле",
    "missing": "обязательное поле не задано",
    "json_invalid": "некорректный JSON",
    "json_type": "некорректный JSON",
    "string_type": "ожидается строка",
    "string_too_short": "не может быть пустым",
    "bool_type": "ожидается true или false",
    "bool_parsing": "ожидается true или false",
    "int_type": "ожидается целое число",
    "int_parsing": "ожидается целое число",
    "float_type": "ожидается число",
    "float_parsing": "ожидается число",
    "list_type": "ожидается список",
    "dict_type": "ожидается объект",
    "model_type": "ожидается объект",
}
_VALIDATION_SHOWN = 3


def validation_summary(exc: ValidationError) -> str:
    """The first errors of `exc` as one Russian line: «поле — что не так; …; и ещё N».

    pydantic's own text is multi-line English with documentation URLs; it is never shown.
    """
    errors = exc.errors(include_url=False, include_input=False, include_context=False)
    parts = []
    for error in errors[:_VALIDATION_SHOWN]:
        where = ".".join(str(part) for part in error["loc"])
        label = _VALIDATION_LABELS.get(error["type"], "недопустимое значение")
        parts.append(f"{where} — {label}" if where else label)
    if len(errors) > _VALIDATION_SHOWN:
        parts.append(f"и ещё {len(errors) - _VALIDATION_SHOWN}")
    return "; ".join(parts)


def user_message(exc: BaseException) -> str:
    """The Russian description of an expected failure (without the leading «Ошибка:»)."""
    if isinstance(exc, PhaseOrderError):
        label = PHASE_LABELS[exc.missing]
        return f"сначала завершите этап «{label}» ({exc.missing.value})"
    if isinstance(exc, PlainError):
        return str(exc)
    if isinstance(exc, ValidationError):
        return f"некорректные данные ({exc.title}): {validation_summary(exc)}"
    for cls, label in _ERROR_LABELS:
        if isinstance(exc, cls):
            return f"{label}: {exc}"
    return str(exc)


__all__ = [
    "ENVIRONMENT_ERRORS",
    "PHASE_LABELS",
    "USER_ERRORS",
    "PlainError",
    "user_message",
    "validation_summary",
]
