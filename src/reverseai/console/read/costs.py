"""LLM costs from the ledger: the same totals as `reverseai costs`."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from reverseai.provenance.ledger import LedgerEvent


@dataclass
class CostRow:
    key: str
    calls: int
    cost_usd: float


@dataclass
class Costs:
    calls: int = 0
    total_usd: float = 0.0
    by_role: list[CostRow] = field(default_factory=list)
    by_model: list[CostRow] = field(default_factory=list)


def summarize_costs(events: list[LedgerEvent]) -> Costs:
    calls = [e.payload for e in events if e.type == "llm.call"]
    by_role: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    by_model: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    total = 0.0
    for payload in calls:
        cost = float(payload.get("cost_usd") or 0.0)
        total += cost
        model = f"{payload.get('model')} ({payload.get('provider')})"
        for key, table in ((str(payload.get("role")), by_role), (model, by_model)):
            table[key][0] += 1
            table[key][1] += cost

    def rows(table: dict[str, list[float]]) -> list[CostRow]:
        return [CostRow(key, int(count), cost) for key, (count, cost) in sorted(table.items())]

    return Costs(calls=len(calls), total_usd=total, by_role=rows(by_role),
                 by_model=rows(by_model))
