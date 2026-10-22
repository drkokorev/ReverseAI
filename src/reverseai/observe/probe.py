"""Active probing of a sandbox target: provoke validation and not-found responses.

Probing writes to the target (POST/PATCH/DELETE), so it only runs against a project whose card
says `target_is_sandbox`. Requests are rate limited and bodies are capped like HAR bodies.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx

from reverseai.observe.contracts import Endpoint
from reverseai.observe.har import MAX_BODY_BYTES, Exchange
from reverseai.project import IntakeError, ProjectCard
from reverseai.provenance.ledger import Ledger

_ACTOR = "observer"
_TIMEOUT_S = 10.0
_NOT_FOUND_ID = "999999"
_LONG_STRING_LENGTH = 201
_WRITE_METHODS = ("POST", "PATCH")
_SAMPLE_BY_TYPE: dict[str, Any] = {
    "string": "sample",
    "integer": 1,
    "number": 1.5,
    "boolean": True,
    "array": [],
    "object": {},
    "null": None,
}


def _types(schema: dict) -> list[str]:
    declared = schema.get("type", [])
    return [declared] if isinstance(declared, str) else list(declared)


def _sample_value(schema: dict) -> Any:
    types = [t for t in _types(schema) if t != "null"] or ["null"]
    return copy.deepcopy(_SAMPLE_BY_TYPE.get(types[0]))


def _wrong_type_value(schema: dict) -> Any:
    """A value whose JSON type is not allowed by `schema`."""
    return 12345 if "string" in _types(schema) else "wrong_type"


def _base_body(endpoint: Endpoint, observed: dict | None) -> dict:
    """A plausible valid body: an observed one if we have it, else one synthesized from schema."""
    if isinstance(observed, dict):
        return copy.deepcopy(observed)
    schema = endpoint.request_schema or {}
    properties = schema.get("properties", {})
    return {name: _sample_value(sub) for name, sub in properties.items()}


def _observed_exchanges(endpoint: Endpoint, exchanges: list[Exchange] | None) -> list[Exchange]:
    ids = set(endpoint.exchange_ids)
    return [e for e in exchanges or [] if e.id in ids]


def _pick_observed(candidates: list[Exchange]) -> Exchange | None:
    """Prefer a successful exchange: its request body is known to be valid."""
    return next((e for e in candidates if 200 <= e.status < 300), candidates[0] if candidates else None)


def _validation_bodies(endpoint: Endpoint, base: dict) -> Iterator[dict]:
    schema = endpoint.request_schema or {}
    properties: dict[str, dict] = schema.get("properties", {})
    yield {}
    for name in schema.get("required", []):
        body = copy.deepcopy(base)
        body.pop(name, None)
        yield body
    for name, sub in properties.items():
        if "string" in _types(sub):
            body = copy.deepcopy(base)
            body[name] = "x" * _LONG_STRING_LENGTH
            yield body
    for name, sub in properties.items():
        body = copy.deepcopy(base)
        body[name] = _wrong_type_value(sub)
        yield body


def _plan(
    endpoint: Endpoint, exchanges: list[Exchange] | None
) -> list[tuple[str, str, dict | None]]:
    """(method, path, json body) probes for one endpoint."""
    has_id = "{id}" in endpoint.path_template
    observed = _pick_observed(_observed_exchanges(endpoint, exchanges))
    is_write = endpoint.method in _WRITE_METHODS
    base = _base_body(endpoint, observed.request_json if observed else None) if is_write else None
    plan: list[tuple[str, str, dict | None]] = []

    can_validate = is_write and endpoint.request_schema is not None
    if can_validate and not has_id:
        plan += [
            (endpoint.method, endpoint.path_template, body)
            for body in _validation_bodies(endpoint, base or {})
        ]
    elif can_validate and endpoint.method == "PATCH" and observed is not None:
        plan += [
            (endpoint.method, observed.path, body)
            for body in _validation_bodies(endpoint, base or {})
        ]

    if has_id:
        plan.append(
            (endpoint.method, endpoint.path_template.replace("{id}", _NOT_FOUND_ID), base)
        )
    return plan


def _read_capped(response: httpx.Response) -> tuple[bytes, bool]:
    """Read at most MAX_BODY_BYTES; the bool says whether the body was longer."""
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            return b"", True
        chunks.append(chunk)
    return b"".join(chunks), False


def _exchange_id(index: int, method: str, url: str) -> str:
    return hashlib.sha256(f"probe:{index}:{method}:{url}".encode()).hexdigest()[:12]


def _send(
    client: httpx.Client, index: int, method: str, url: str, body: dict | None
) -> Exchange:
    parts = urlsplit(url)
    base: dict[str, Any] = {
        "id": _exchange_id(index, method, url),
        "method": method,
        "url": url,
        "path": parts.path,
        "query": dict(parse_qsl(parts.query, keep_blank_values=True)),
        "request_json": body,
    }
    try:
        with client.stream(method, url, json=body) as response:
            raw, too_large = _read_capped(response)
            status = response.status_code
            content_type = response.headers.get("content-type", "")
    except httpx.HTTPError:
        return Exchange(
            **base, status=0, response_json=None, response_content_type="", error="unreachable"
        )

    media_type = content_type.split(";", 1)[0].strip().lower()
    response_json: Any | None = None
    error: str | None = None
    if too_large:
        error = "body_too_large"
    elif "json" in media_type and raw.strip():
        try:
            response_json = json.loads(raw)
        except (ValueError, RecursionError):
            error = "invalid_json"
    return Exchange(
        **base,
        status=status,
        response_json=response_json,
        response_content_type=media_type,
        error=error,
    )


def probe_endpoints(
    base_url: str,
    endpoints: list[Endpoint],
    card: ProjectCard,
    *,
    client: httpx.Client | None = None,
    delay_s: float = 0.5,
    exchanges: list[Exchange] | None = None,
    ledger: Ledger | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Exchange]:
    """Send validation and not-found probes to `endpoints`; return one Exchange per request.

    For POST/PATCH endpoints with a request schema (and no `{id}` in the path, or PATCH with an
    observed concrete path): an empty object, each required field removed, each string field
    overlong, each field of the wrong type. For every `{id}` endpoint: id 999999.
    Unreachable targets are recorded as `error="unreachable"`, never raised.
    """
    if not card.target_is_sandbox:
        raise IntakeError("probing writes to the target and requires card.target_is_sandbox")
    host = (urlsplit(base_url).hostname or "").lower()
    if host not in {d.lower() for d in card.allowed_domains}:
        raise IntakeError(f"probe host {host!r} is not in allowed_domains")

    own_client = client is None
    http = client or httpx.Client(trust_env=False, timeout=_TIMEOUT_S)
    results: list[Exchange] = []
    try:
        for endpoint in endpoints:
            for method, path, body in _plan(endpoint, exchanges):
                if results:
                    sleep(delay_s)
                url = base_url.rstrip("/") + path
                results.append(_send(http, len(results), method, url, body))
    finally:
        if own_client:
            http.close()

    if ledger is not None:
        ledger.append("observe.probe", "dirty", _ACTOR, {"count": len(results)})
    return results
