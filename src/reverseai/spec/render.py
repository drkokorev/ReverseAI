"""Render a behavior spec as Russian-language markdown."""

from __future__ import annotations

import json

from reverseai.spec.model import ApiContract, BehaviorSpec, Entity, SpecItem


def _item_line(item: SpecItem) -> str:
    line = (
        f"- **{item.id} {item.title}** (уверенность: {item.confidence}) — {item.description}"
    )
    if item.evidence:
        refs = ", ".join(f"{e.kind}:{e.ref}" for e in item.evidence)
        line += f" [evidence: {refs}]"
    return line


def _entity_block(entity: Entity) -> list[str]:
    lines = [f"- **{entity.name}** — {entity.description}"]
    lines += [f"  - `{name}`: {kind}" for name, kind in entity.fields.items()]
    return lines


def _api_block(contract: ApiContract) -> list[str]:
    head = f"- **{contract.method} {contract.path}**"
    if contract.description:
        head += f" — {contract.description}"
    lines = [head]
    if contract.request_schema:
        lines.append(f"  - запрос: `{_compact(contract.request_schema)}`")
    for status in sorted(contract.responses):
        lines.append(f"  - ответ {status}: `{_compact(contract.responses[status])}`")
    return lines


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_markdown(spec: BehaviorSpec) -> str:
    lines = [f"# {spec.product_name} — поведенческая спецификация v{spec.version}", ""]
    lines += ["## Обзор", "", spec.summary or "—", ""]
    lines += ["## Функции", ""]
    lines += [_item_line(i) for i in spec.features] or ["—"]
    lines += ["", "## Сущности", ""]
    for entity in spec.entities:
        lines += _entity_block(entity)
    if not spec.entities:
        lines.append("—")
    lines += ["", "## Правила", ""]
    lines += [_item_line(i) for i in spec.rules] or ["—"]
    lines += ["", "## API", ""]
    for contract in spec.api:
        lines += _api_block(contract)
    if not spec.api:
        lines.append("—")
    lines += ["", "## Пробелы", ""]
    lines += [f"- {gap}" for gap in spec.gaps] or ["—"]
    return "\n".join(lines) + "\n"
