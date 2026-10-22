"""Form input: the new-project form (a ProjectCard) and numeric phase options.

Errors are translated sentences shown next to the form.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from reverseai.i18n import CATALOGS, DEFAULT_LANG, Labels, t
from reverseai.messages import user_message, validation_summary
from reverseai.project import Attestation, IntakeError, Mode, ProjectCard

JURISDICTIONS: Labels[str] = Labels("jurisdiction", ["us", "eu", "cn", "self"])
DEFAULT_JURISDICTIONS = ("us", "eu", "self")
MODE_OPTIONS: Labels[str] = Labels("mode_option", [m.value for m in Mode])


class FormError(ValueError):
    """Invalid form input; the message is a translated sentence for the user."""


def intake_message(exc: IntakeError) -> str:
    """The form's wording of the intake gate's refusal (falls back to the CLI's message)."""
    key = f"form.intake.{exc.key}"
    if key in CATALOGS[DEFAULT_LANG]:
        return t(key, **exc.params)
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
            raise FormError(t("form.name_required"))
        if self.mode not in MODE_OPTIONS:
            raise FormError(t("form.unknown_mode"))
        if not self.target_base_url.strip():
            raise FormError(t("form.url_required"))
        domains = [d.lower() for d in _items(self.allowed_domains)]
        if not domains:
            raise FormError(t("form.domains_required"))
        if not self.product_name.strip():
            raise FormError(t("form.product_required"))
        jurisdictions = [j for j in self.jurisdictions if j in JURISDICTIONS]
        if not jurisdictions:
            raise FormError(t("form.jurisdiction_required"))
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
            raise FormError(t("form.invalid_card", summary=validation_summary(exc))) from exc


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
