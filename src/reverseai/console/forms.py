"""Form input: the new-project form (a ProjectCard) and numeric phase options.

Errors are Russian sentences shown next to the form.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from reverseai.messages import user_message, validation_summary
from reverseai.project import Attestation, IntakeError, Mode, ProjectCard

JURISDICTIONS: dict[str, str] = {
    "us": "США",
    "eu": "ЕС",
    "cn": "Китай",
    "self": "Собственный хостинг",
}
DEFAULT_JURISDICTIONS = ("us", "eu", "self")
MODE_OPTIONS: dict[str, str] = {
    Mode.LEGACY.value: "Legacy (замена системы)",
    Mode.IMPORT_SUBSTITUTION.value: "Импортозамещение",
}

_INTAKE_MESSAGES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"attestation of lawful access is required"),
     "Нужно подтвердить законность доступа к цели."),
    (re.compile(r"target host ['\"](.*)['\"] is not in allowed_domains"),
     "Хост цели «{0}» не входит в разрешённые домены."),
    (re.compile(r"product name ['\"](.*)['\"] reuses a brand term"),
     "Название продукта «{0}» повторяет бренд оригинала."),
    (re.compile(r"project directory already exists"),
     "Проект с таким именем уже существует."),
    (re.compile(r"has no usable characters"),
     "В названии проекта нет букв или цифр."),
]


class FormError(ValueError):
    """Invalid form input; the message is a Russian sentence for the user."""


def intake_message(exc: IntakeError) -> str:
    """Russian wording of the intake gate's refusal (falls back to the CLI's message)."""
    text = str(exc)
    for pattern, message in _INTAKE_MESSAGES:
        match = pattern.search(text)
        if match:
            return message.format(*match.groups())
    return user_message(exc)


def _items(text: str) -> list[str]:
    """Comma- or newline-separated values, trimmed, empty ones dropped, order kept."""
    return [item.strip() for item in re.split(r"[,\n]", text) if item.strip()]


@dataclass
class NewProjectForm:
    name: str = ""
    mode: str = Mode.LEGACY.value
    target_base_url: str = ""
    allowed_domains: str = ""
    target_is_sandbox: bool = False
    product_name: str = ""
    brand_terms: str = ""
    jurisdictions: list[str] = field(default_factory=lambda: list(DEFAULT_JURISDICTIONS))
    jurisdiction: str = "RU"
    lawful_access: bool = False
    basis: str = ""
    signed_by: str = ""
    signed_at: str = ""

    def card(self) -> ProjectCard:
        """The project card; FormError for anything the form itself can tell is wrong."""
        if not self.name.strip():
            raise FormError("Укажите название проекта.")
        if self.mode not in MODE_OPTIONS:
            raise FormError("Неизвестный режим проекта.")
        if not self.target_base_url.strip():
            raise FormError("Укажите адрес цели.")
        domains = [d.lower() for d in _items(self.allowed_domains)]
        if not domains:
            raise FormError("Укажите хотя бы один разрешённый домен.")
        if not self.product_name.strip():
            raise FormError("Укажите название продукта клона.")
        jurisdictions = [j for j in self.jurisdictions if j in JURISDICTIONS]
        if not jurisdictions:
            raise FormError("Выберите хотя бы одну юрисдикцию.")
        signed_at = self.signed_at.strip() or dt.datetime.now(dt.UTC).isoformat()
        try:
            return ProjectCard.model_validate(
                {
                    "name": self.name.strip(),
                    "mode": self.mode,
                    "target_base_url": self.target_base_url.strip(),
                    "allowed_domains": domains,
                    "target_is_sandbox": self.target_is_sandbox,
                    "attestation": Attestation(
                        lawful_access=self.lawful_access,
                        basis=self.basis.strip(),
                        signed_by=self.signed_by.strip(),
                        signed_at=signed_at,
                    ),
                    "data_policy": {"allowed_jurisdictions": jurisdictions},
                    "jurisdiction": self.jurisdiction.strip() or "RU",
                    "brand_terms": _items(self.brand_terms),
                    "product_name": self.product_name.strip(),
                }
            )
        except ValidationError as exc:
            raise FormError(f"Некорректные данные карточки: {validation_summary(exc)}.") from exc


def positive_int(raw: str, default: int, message: str) -> int:
    """`raw` as an integer ≥ 1 (`default` when empty); FormError(message) otherwise."""
    if not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise FormError(message) from None
    if value < 1:
        raise FormError(message)
    return value
