"""Build a behavior spec from an observation bundle: analyst LLM, critic LLM, one revision."""

from __future__ import annotations

import json

from pydantic import BaseModel

from reverseai.llm.gateway import Gateway
from reverseai.llm.jsonout import LLMOutputError, complete_json
from reverseai.llm.policy import DataPolicy
from reverseai.llm.types import Message
from reverseai.observe.bundle import ObservationBundle
from reverseai.observe.contracts import Endpoint
from reverseai.spec.model import AnalystDraft, ApiContract, BehaviorSpec
from reverseai.zones.store import Zone

ANALYST_ACTOR = "spec.analyst"
CRITIC_ACTOR = "spec.critic"

_ANALYST_SYSTEM = """[role:analyst]
You are a behavior analyst. You study observations of a web product (pages, API exchanges, \
probe results, public docs) and write a behavior specification that another team will use to \
build a functionally equivalent product without ever seeing the original.

This specification is the ONLY thing that crosses the clean-room barrier, so:
- Describe behavior and rules in your own words. Never copy code, markup, UI wording, error \
message prose, slogans or brand names from the observations.
- Use the product name given in the request; never the name of the observed product.
- Machine identifiers needed for compatibility ARE allowed and encouraged: JSON field names, \
error codes, enum values, paths, HTTP methods and status codes.
- Be precise and testable: state inputs, outputs, defaults, limits, normalization, ordering, \
status codes and error codes. Prefer concrete rules over vague prose.
- Mark everything you could not observe as a gap. Do not invent behavior; lower the \
confidence instead.
- Cite evidence for every feature and rule using refs taken from the observations: page URLs \
(kind "page"), endpoints written as "METHOD /path/template" (kind "endpoint"), exchange ids \
(kind "exchange"), documentation (kind "doc").

Reply with a single JSON object and nothing else, in exactly this shape:
{"summary": str,
 "features": [{"id": str, "title": str, "description": str, "confidence": "high|medium|low", \
"evidence": [{"kind": "page|exchange|endpoint|doc|expert", "ref": str}]}],
 "entities": [{"name": str, "fields": {"<field>": "<type and meaning>"}, "description": str}],
 "rules": [same item shape as features],
 "gaps": [str]}
The HTTP API contracts are derived separately from the observed traffic; do not repeat them as \
a list, but do describe their behavior (validation, errors, defaults) as rules."""

_CRITIC_SYSTEM = """[role:spec_critic]
You are a strict reviewer of a behavior specification. Compare the specification with the \
observations it was built from and list concrete problems:
- claims not supported by the observations, or contradicting them;
- observed behavior, fields, status codes or error codes that the specification omits;
- vague statements that a developer could not implement or test;
- copied code, UI wording, error message prose or brand names (machine identifiers such as \
JSON field names and error codes are fine);
- features or rules without evidence, or with evidence refs that do not appear in the \
observations.
Reply with a single JSON object and nothing else: {"issues": [str]}. Each issue is one short \
self-contained sentence. Your issues are copied into the specification, so refer to problems by \
item id or field name; never quote observed text, wording, code or names in an issue. If the specification is sound, reply {"issues": []}."""


class _CriticReport(BaseModel):
    issues: list[str]


def _api_contracts(endpoints: list[Endpoint]) -> list[ApiContract]:
    return [
        ApiContract(
            method=e.method,
            path=e.path_template,
            request_schema=e.request_schema,
            responses=dict(e.response_schemas),
            description="",
        )
        for e in endpoints
    ]


def _assemble(
    product_name: str, draft: AnalystDraft, api: list[ApiContract]
) -> BehaviorSpec:
    return BehaviorSpec(
        product_name=product_name,
        summary=draft.summary,
        features=draft.features,
        entities=draft.entities,
        rules=draft.rules,
        api=api,
        gaps=list(draft.gaps),
    )


def _analyst_request(bundle: ObservationBundle, product_name: str) -> str:
    return (
        f"Product name to use in the specification: {product_name}\n\n"
        f"Observations:\n\n{bundle.to_prompt()}"
    )


def critique_spec(
    gateway: Gateway,
    spec: BehaviorSpec,
    bundle: ObservationBundle,
    *,
    policy: DataPolicy,
) -> list[str]:
    """Ask the critic role for issues in `spec`; empty list means no objections."""
    content = (
        f"Specification (JSON):\n{spec.model_dump_json(indent=1)}\n\n"
        f"Observations:\n\n{bundle.to_prompt()}"
    )
    report = complete_json(
        gateway,
        "spec_critic",
        [Message(role="user", content=content)],
        model_cls=_CriticReport,
        system=_CRITIC_SYSTEM,
        policy=policy,
        zone=Zone.DIRTY,
        actor=CRITIC_ACTOR,
    )
    return [issue for issue in report.issues if issue.strip()]


def build_spec(
    gateway: Gateway,
    bundle: ObservationBundle,
    *,
    product_name: str,
    policy: DataPolicy,
) -> BehaviorSpec:
    """Analyst draft, critic review, at most one revision; leftover critic issues become gaps."""
    request = Message(role="user", content=_analyst_request(bundle, product_name))
    draft = complete_json(
        gateway,
        "analyst",
        [request],
        model_cls=AnalystDraft,
        system=_ANALYST_SYSTEM,
        policy=policy,
        zone=Zone.DIRTY,
        actor=ANALYST_ACTOR,
    )
    api = _api_contracts(bundle.endpoints)
    spec = _assemble(product_name, draft, api)

    issues = critique_spec(gateway, spec, bundle, policy=policy)
    if not issues:
        return spec

    revision = Message(
        role="user",
        content=(
            "A reviewer found problems in your draft. Fix those that the observations "
            "support, mark what cannot be confirmed as a gap, and reply with the complete "
            "corrected JSON object in the same shape.\n\n"
            f"Issues:\n{json.dumps(issues, ensure_ascii=False, indent=1)}"
        ),
    )
    try:
        revised = complete_json(
            gateway,
            "analyst",
            [request, Message(role="assistant", content=draft.model_dump_json()), revision],
            model_cls=AnalystDraft,
            system=_ANALYST_SYSTEM,
            policy=policy,
            zone=Zone.DIRTY,
            actor=ANALYST_ACTOR,
        )
    except LLMOutputError:
        # the revision is best effort: keep the first draft, the issues still become gaps
        revised = draft
    spec = _assemble(product_name, revised, api)
    spec.gaps.extend(f"critic: {issue}" for issue in issues)
    return spec
