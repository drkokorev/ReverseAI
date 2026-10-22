"""Infer API contracts (endpoints and JSON schemas) from observed exchanges."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from reverseai.observe.har import Exchange

_ID_SEGMENT = re.compile(
    r"[0-9]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE | re.ASCII,
)
_DATETIME_PREFIX = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", re.ASCII)


class Endpoint(BaseModel):
    method: str
    path_template: str
    statuses: list[int]
    request_schema: dict | None
    response_schemas: dict[int, dict]
    exchange_ids: list[str]


def template_path(path: str) -> str:
    """Replace all-digit and UUID path segments with `{id}`."""
    return "/".join("{id}" if _ID_SEGMENT.fullmatch(seg) else seg for seg in path.split("/"))


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _is_iso_datetime(value: str) -> bool:
    if not _DATETIME_PREFIX.match(value):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def infer_schema(examples: list[Any]) -> dict:
    """Infer a JSON-schema subset (type, properties, required, items, format) from examples."""
    if not examples:
        return {}
    types = {_json_type(e) for e in examples}
    if "number" in types:
        types.discard("integer")
    schema: dict[str, Any] = {"type": next(iter(types)) if len(types) == 1 else sorted(types)}

    objects = [e for e in examples if isinstance(e, dict)]
    if objects:
        values: dict[str, list[Any]] = defaultdict(list)
        for obj in objects:
            for key, value in obj.items():
                values[key].append(value)
        schema["properties"] = {key: infer_schema(values[key]) for key in sorted(values)}
        schema["required"] = sorted(k for k in values if len(values[k]) == len(objects))

    arrays = [e for e in examples if isinstance(e, list)]
    if arrays:
        schema["items"] = infer_schema([item for arr in arrays for item in arr])

    strings = [e for e in examples if isinstance(e, str)]
    if strings and all(_is_iso_datetime(s) for s in strings):
        schema["format"] = "date-time"
    return schema


def infer_endpoints(exchanges: list[Exchange]) -> list[Endpoint]:
    """Group error-free exchanges by (method, templated path) and infer their schemas."""
    groups: dict[tuple[str, str], list[Exchange]] = defaultdict(list)
    for ex in exchanges:
        if ex.error is None:
            groups[(ex.method, template_path(ex.path))].append(ex)

    endpoints = []
    for (method, template), group in sorted(groups.items()):
        request_examples = [e.request_json for e in group if e.request_json is not None]
        by_status: dict[int, list[Any]] = defaultdict(list)
        for ex in group:
            examples = by_status[ex.status]
            if ex.response_json is not None:
                examples.append(ex.response_json)
        endpoints.append(
            Endpoint(
                method=method,
                path_template=template,
                statuses=sorted(by_status),
                request_schema=infer_schema(request_examples) if request_examples else None,
                response_schemas={s: infer_schema(by_status[s]) for s in sorted(by_status)},
                exchange_ids=[e.id for e in group],
            )
        )
    return endpoints
