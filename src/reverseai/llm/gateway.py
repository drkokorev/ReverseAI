"""LLM gateway: role routing, data policy, retry/fallback, cost accounting and transcripts."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from reverseai.config import ModelSpec, Settings
from reverseai.llm.policy import DataPolicy, PolicyViolation
from reverseai.llm.types import (
    LLMRequest,
    LLMResponse,
    Message,
    Provider,
    ProviderError,
    Usage,
)
from reverseai.provenance.ledger import Ledger
from reverseai.zones.store import Zone

_MAX_SUMMARY_CHARS = 300


class GatewayError(Exception):
    """Raised when no candidate model could serve a request."""


@dataclass
class CostSummary:
    total_usd: float = 0.0
    by_role: dict[str, float] = field(default_factory=dict)
    by_model: dict[str, float] = field(default_factory=dict)
    calls: int = 0


def cost_usd(model: ModelSpec, usage: Usage) -> float:
    """Price of one call; ``usage.input_tokens`` is the total prompt size incl. cached tokens."""
    cached = min(max(usage.cached_input_tokens, 0), usage.input_tokens)
    fresh = usage.input_tokens - cached
    return (
        fresh * model.input_per_mtok
        + cached * model.cached_input_per_mtok
        + usage.output_tokens * model.output_per_mtok
    ) / 1_000_000


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _prompt_hash(system: str | None, messages: list[Message]) -> str:
    canonical = json.dumps(
        {"system": system, "messages": [asdict(m) for m in messages]},
        sort_keys=True,
        ensure_ascii=False,
    )
    return _sha256(canonical)


class Gateway:
    def __init__(
        self,
        settings: Settings,
        providers: dict[str, Provider],
        ledger: Ledger,
        *,
        retries_per_candidate: int = 2,
        sleep: Callable[[float], None] = time.sleep,
        transcripts_dir: Path | None = None,
    ):
        self._settings = settings
        self._providers = providers
        self._ledger = ledger
        self._retries = retries_per_candidate
        self._sleep = sleep
        self._transcripts_dir = (
            Path(transcripts_dir) if transcripts_dir is not None else None
        )
        self._lock = threading.Lock()
        self._calls = 0
        self._by_role: dict[str, float] = defaultdict(float)
        self._by_model: dict[str, float] = defaultdict(float)

    def costs(self) -> CostSummary:
        with self._lock:
            return CostSummary(
                total_usd=sum(self._by_role.values()),
                by_role=dict(self._by_role),
                by_model=dict(self._by_model),
                calls=self._calls,
            )

    def complete(
        self,
        role: str,
        messages: list[Message],
        *,
        system: str | None = None,
        policy: DataPolicy,
        zone: Zone,
        actor: str,
    ) -> LLMResponse:
        role_spec = self._settings.roles.get(role)
        if role_spec is None:
            self._fail(
                role, zone, actor, [], [f"unknown role {role!r}"], "unknown_role"
            )
            raise GatewayError(f"unknown role {role!r}")

        usable = [
            name
            for name in role_spec.candidates
            if self._settings.models[name].provider in self._providers
        ]
        allowed = [
            name
            for name in usable
            if self._settings.providers[
                self._settings.models[name].provider
            ].jurisdiction
            in policy.allowed_jurisdictions
        ]
        if not allowed:
            message = (
                f"no candidate for role {role!r} satisfies the data policy "
                f"(available: {usable}, allowed jurisdictions: "
                f"{sorted(policy.allowed_jurisdictions)})"
            )
            self._fail(role, zone, actor, [], [message], "policy_violation")
            raise PolicyViolation(message)

        tried: list[str] = []
        errors: list[str] = []
        attempts = 0
        for name in allowed:
            model = self._settings.models[name]
            provider = self._providers[model.provider]
            request = LLMRequest(
                model=name,
                system=system,
                messages=list(messages),
                max_tokens=role_spec.max_output_tokens,
            )
            tried.append(name)
            for attempt in range(self._retries + 1):
                attempts += 1
                try:
                    response = provider.complete(request)
                except ProviderError as exc:
                    errors.append(f"{name}: {str(exc)[:_MAX_SUMMARY_CHARS]}")
                    if not exc.retryable or attempt >= self._retries:
                        break
                    self._sleep(2**attempt)
                    continue
                return self._record(
                    role, model, request, response, attempts, zone, actor
                )

        self._fail(role, zone, actor, tried, errors, "all_candidates_failed")
        raise GatewayError(
            f"all candidates failed for role {role!r}: tried {tried}; errors: {errors}"
        )

    def _record(
        self,
        role: str,
        model: ModelSpec,
        request: LLMRequest,
        response: LLMResponse,
        attempts: int,
        zone: Zone,
        actor: str,
    ) -> LLMResponse:
        cost = cost_usd(model, response.usage)
        response = replace(response, cost_usd=cost)
        event = self._ledger.append(
            "llm.call",
            str(zone),
            actor,
            {
                "role": role,
                "model": model.id,
                "provider": model.provider,
                "usage": asdict(response.usage),
                "cost_usd": cost,
                "prompt_sha256": _prompt_hash(request.system, request.messages),
                "response_sha256": _sha256(response.text),
                "attempts": attempts,
            },
        )
        with self._lock:
            self._calls += 1
            self._by_role[role] += cost
            self._by_model[model.id] += cost
        if self._transcripts_dir is not None:
            self._write_transcript(event.seq, role, request, response, zone, actor)
        return response

    def _write_transcript(
        self,
        seq: int,
        role: str,
        request: LLMRequest,
        response: LLMResponse,
        zone: Zone,
        actor: str,
    ) -> None:
        assert self._transcripts_dir is not None
        self._transcripts_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "role": role,
            "zone": str(zone),
            "actor": actor,
            "request": {
                "model": request.model,
                "system": request.system,
                "messages": [asdict(m) for m in request.messages],
                "max_tokens": request.max_tokens,
            },
            "response": {
                "text": response.text,
                "usage": asdict(response.usage),
                "cost_usd": response.cost_usd,
            },
        }
        (self._transcripts_dir / f"{seq}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _fail(
        self,
        role: str,
        zone: Zone,
        actor: str,
        tried: list[str],
        errors: list[str],
        kind: str,
    ) -> None:
        # Never the prompt text: only role, model names and (already key-scrubbed) error summaries.
        self._ledger.append(
            "llm.error",
            str(zone),
            actor,
            {"role": role, "kind": kind, "tried_models": tried, "errors": errors},
        )
