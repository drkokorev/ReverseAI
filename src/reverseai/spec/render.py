"""Render a behavior spec as markdown (headings in the active or the given language)."""

from __future__ import annotations

import json

from reverseai.i18n import t
from reverseai.spec.model import ApiContract, BehaviorSpec, Entity, SpecItem


def _item_line(item: SpecItem, lang: str | None) -> str:
    confidence = t("spec_md.confidence", lang=lang, confidence=item.confidence)
    line = f"- **{item.id} {item.title}** ({confidence}) — {item.description}"
    if item.evidence:
        refs = ", ".join(f"{e.kind}:{e.ref}" for e in item.evidence)
        line += f" [evidence: {refs}]"
    return line


def _entity_block(entity: Entity) -> list[str]:
    lines = [f"- **{entity.name}** — {entity.description}"]
    lines += [f"  - `{name}`: {kind}" for name, kind in entity.fields.items()]
    return lines


def _api_block(contract: ApiContract, lang: str | None) -> list[str]:
    head = f"- **{contract.method} {contract.path}**"
    if contract.description:
        head += f" — {contract.description}"
    lines = [head]
    if contract.request_schema:
        request = t("spec_md.request", lang=lang)
        lines.append(f"  - {request}: `{_compact(contract.request_schema)}`")
    for status in sorted(contract.responses):
        response = t("spec_md.response", lang=lang, status=status)
        lines.append(f"  - {response}: `{_compact(contract.responses[status])}`")
    return lines


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_markdown(spec: BehaviorSpec, lang: str | None = None) -> str:
    """The spec as markdown; `lang` defaults to the active language."""

    def heading(key: str) -> str:
        return "## " + t(f"spec_md.{key}", lang=lang)

    title = t("spec_md.title", lang=lang, product=spec.product_name, version=spec.version)
    lines = [f"# {title}", ""]
    lines += [heading("overview"), "", spec.summary or "—", ""]
    lines += [heading("features"), ""]
    lines += [_item_line(i, lang) for i in spec.features] or ["—"]
    lines += ["", heading("entities"), ""]
    for entity in spec.entities:
        lines += _entity_block(entity)
    if not spec.entities:
        lines.append("—")
    lines += ["", heading("rules"), ""]
    lines += [_item_line(i, lang) for i in spec.rules] or ["—"]
    lines += ["", heading("api"), ""]
    for contract in spec.api:
        lines += _api_block(contract, lang)
    if not spec.api:
        lines.append("—")
    lines += ["", heading("gaps"), ""]
    lines += [f"- {gap}" for gap in spec.gaps] or ["—"]
    return "\n".join(lines) + "\n"
