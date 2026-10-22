"""Extract and validate JSON from LLM output, with one repair retry."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from reverseai.llm.gateway import Gateway
from reverseai.llm.policy import DataPolicy
from reverseai.llm.types import Message
from reverseai.zones.store import Zone

_FENCE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_PAIRS = (("{", "}"), ("[", "]"))


class LLMOutputError(Exception):
    """LLM output could not be parsed or validated as the requested JSON."""


_MAX_SCAN_STARTS = 2_000  # opener positions tried by the last-resort scan


def _try_load(text: str) -> tuple[bool, Any]:
    try:
        return True, json.loads(text)
    except (ValueError, RecursionError):  # RecursionError: absurdly deep nesting
        return False, None


def _scan(text: str) -> tuple[bool, Any]:
    """Longest JSON value that starts at some ``{``/``[`` of ``text`` (prose around it)."""
    decoder = json.JSONDecoder()
    found = False
    best: Any = None
    best_start = best_end = -1
    starts = [i for i, ch in enumerate(text) if ch in "{["][:_MAX_SCAN_STARTS]
    for start in starts:
        if start < best_end:
            continue  # inside the value already found: it cannot be longer
        try:
            value, end = decoder.raw_decode(text, start)
        except (ValueError, RecursionError):
            continue
        if not found or end - start > best_end - best_start:
            found, best, best_start, best_end = True, value, start, end
    return found, best


def extract_json(text: str) -> Any:
    """Parse JSON from ``text``: whole text, then a fenced block, then the outermost span.

    Spans from the first ``{``/``[`` to the last ``}``/``]`` are tried longest first, so a
    bracketed aside (``Note [1]: {...}``) never wins over the object; if neither parses, the
    longest value that starts at any bracket is taken.
    """
    ok, value = _try_load(text.strip())
    if ok:
        return value
    for match in _FENCE.finditer(text):
        ok, value = _try_load(match.group(1).strip())
        if ok:
            return value
    spans = []
    for opener, closer in _PAIRS:
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            spans.append((start, end))
    for start, end in sorted(spans, key=lambda span: span[0] - span[1]):
        ok, value = _try_load(text[start : end + 1])
        if ok:
            return value
    ok, value = _scan(text)
    if ok:
        return value
    raise LLMOutputError("no valid JSON found in LLM output")


def _parse(text: str, model_cls: type[BaseModel] | None) -> Any:
    data = extract_json(text)
    if model_cls is None:
        return data
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise LLMOutputError(
            f"JSON does not match {model_cls.__name__}: {exc}"
        ) from exc


def complete_json(
    gateway: Gateway,
    role: str,
    messages: list[Message],
    *,
    model_cls: type[BaseModel] | None = None,
    system: str | None = None,
    policy: DataPolicy,
    zone: Zone,
    actor: str,
) -> Any:
    """Call the gateway and parse JSON; on invalid output retry once with a repair prompt."""
    kwargs: dict[str, Any] = {
        "system": system,
        "policy": policy,
        "zone": zone,
        "actor": actor,
    }
    response = gateway.complete(role, messages, **kwargs)
    try:
        return _parse(response.text, model_cls)
    except LLMOutputError as first_error:
        repair = [
            *messages,
            Message(role="assistant", content=response.text),
            Message(
                role="user",
                content=f"Your previous output was invalid: {first_error}. "
                "Reply with valid JSON only.",
            ),
        ]
    retry = gateway.complete(role, repair, **kwargs)
    try:
        return _parse(retry.text, model_cls)
    except LLMOutputError as exc:
        raise LLMOutputError(
            f"LLM output invalid after one repair retry: {exc}"
        ) from exc
