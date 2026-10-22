"""Parse a HAR recording into classified assets and API exchanges.

Only behavior (HTTP exchanges) becomes `Exchange`s. Anything that is the target's own code
(JS/CSS/WASM/source maps, HTML) is kept verbatim as `ExpressionAsset` for the dirty zone and is
never interpreted here (D-005).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel

MAX_BODY_BYTES = 2_000_000
MAX_EXPRESSION_BYTES = 20_000_000  # cap for expression/document assets (bundles are big)

_EXPRESSION_EXTENSIONS = (".js", ".mjs", ".css", ".wasm", ".map")


class AssetClass(StrEnum):
    API = "api"
    DOCUMENT = "document"
    EXPRESSION = "expression"
    MEDIA = "media"
    OTHER = "other"


class Exchange(BaseModel):
    id: str
    method: str
    url: str
    path: str
    query: dict[str, str]
    status: int
    request_json: Any | None
    response_json: Any | None
    response_content_type: str
    error: str | None = None


class ExpressionAsset(BaseModel):
    url: str
    content: str


class HarParseResult(BaseModel):
    exchanges: list[Exchange]
    expression: list[ExpressionAsset]
    documents: list[ExpressionAsset]
    dropped_media: int
    out_of_scope: int
    dropped_assets: list[str] = []


def _media_type(content_type: str) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return "" if media_type == "x-unknown" else media_type


def classify(content_type: str, url: str) -> AssetClass:
    """Classify a response by its URL extension first, then by content type."""
    path = urlsplit(url).path.lower()
    media_type = _media_type(content_type)
    if (
        path.endswith(_EXPRESSION_EXTENSIONS)
        or "javascript" in media_type
        or "ecmascript" in media_type
        or "wasm" in media_type
        or media_type == "text/css"
    ):
        return AssetClass.EXPRESSION
    if media_type.split("/", 1)[0] in ("image", "font", "audio", "video"):
        return AssetClass.MEDIA
    if media_type in ("text/html", "application/xhtml+xml"):
        return AssetClass.DOCUMENT
    if media_type.endswith("json"):
        return AssetClass.API
    return AssetClass.OTHER


def _header(headers: Any, name: str) -> str:
    if not isinstance(headers, list):
        return ""
    for h in headers:
        if isinstance(h, dict) and str(h.get("name", "")).lower() == name:
            return str(h.get("value", ""))
    return ""


def _decode(
    text: Any, encoding: Any, size: Any, limit: int = MAX_BODY_BYTES
) -> tuple[bytes | None, str | None]:
    """Return (raw bytes or None, error). Size is checked on the decoded bytes."""
    if not isinstance(text, str):
        if isinstance(size, int) and size > limit:
            return None, "body_too_large"
        return None, None
    if encoding == "base64":
        try:
            raw = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            return None, "invalid_json"
    else:
        raw = text.encode("utf-8", errors="replace")
    if len(raw) > limit:
        return None, "body_too_large"
    return raw, None


def _parse_json(raw: bytes) -> tuple[Any | None, bool]:
    """Return (value, ok). An empty body is ok with value None."""
    if not raw.strip():
        return None, True
    try:
        return json.loads(raw), True
    except (ValueError, RecursionError):
        return None, False


def _is_json(media_type: str) -> bool:
    return "json" in media_type.lower()


def _request_json(request: dict[str, Any]) -> tuple[Any | None, str | None, bool]:
    """Return (request_json, error, had_json_body)."""
    post = request.get("postData")
    if not isinstance(post, dict) or not post.get("text"):
        return None, None, False
    mime = str(post.get("mimeType") or "") or _header(request.get("headers"), "content-type")
    if not _is_json(mime):
        return None, None, False
    raw, error = _decode(post.get("text"), post.get("encoding"), None)
    if error == "body_too_large":
        return None, error, True
    if raw is None:
        return None, None, True
    value, _ = _parse_json(raw)
    return value, None, True


def _exchange_id(index: int, method: str, url: str) -> str:
    return hashlib.sha256(f"{index}:{method}:{url}".encode()).hexdigest()[:12]


def _looks_like_api_request(path: str, had_json_body: bool, request: dict[str, Any]) -> bool:
    accept = _header(request.get("headers"), "accept")
    return path.startswith("/api") or had_json_body or "json" in accept.lower()


def parse_har(har: dict[str, Any], allowed_domains: list[str]) -> HarParseResult:
    """Split HAR entries into API exchanges, expression/document assets and counters.

    Entries whose host is not in `allowed_domains` are counted in `out_of_scope` and dropped.
    """
    allowed = {d.lower() for d in allowed_domains}
    log = har.get("log", har)
    entries = log.get("entries", []) if isinstance(log, dict) else []

    exchanges: list[Exchange] = []
    expression: list[ExpressionAsset] = []
    documents: list[ExpressionAsset] = []
    dropped_media = 0
    out_of_scope = 0
    dropped_assets: list[str] = []

    for index, entry in enumerate(entries):
        request = entry.get("request", {})
        response = entry.get("response", {})
        content = response.get("content") or {}
        url = str(request.get("url", ""))
        try:
            parts = urlsplit(url)
            hostname = (parts.hostname or "").lower()
        except ValueError:
            hostname = ""
        if not hostname or hostname not in allowed:
            out_of_scope += 1
            continue

        method = str(request.get("method", "GET")).upper()
        status = int(response.get("status", 0) or 0)
        content_type = _header(response.get("headers"), "content-type") or str(
            content.get("mimeType") or ""
        )
        asset_class = classify(content_type, url)

        if asset_class is AssetClass.MEDIA:
            dropped_media += 1
            continue

        is_asset = asset_class in (AssetClass.EXPRESSION, AssetClass.DOCUMENT)
        raw, body_error = _decode(
            content.get("text"),
            content.get("encoding"),
            content.get("size"),
            MAX_EXPRESSION_BYTES if is_asset else MAX_BODY_BYTES,
        )

        if is_asset:
            if body_error:
                dropped_assets.append(url)
            elif raw:
                asset = ExpressionAsset(url=url, content=raw.decode("utf-8", errors="replace"))
                target = expression if asset_class is AssetClass.EXPRESSION else documents
                target.append(asset)
            continue

        request_json, request_error, had_json_body = _request_json(request)
        response_json: Any | None = None
        error = body_error

        if asset_class is AssetClass.API:
            if raw is not None:
                response_json, ok = _parse_json(raw)
                if not ok:
                    error = "invalid_json"
        elif _media_type(content_type) == "":
            # No usable content type: the body decides.
            if raw and raw.strip():
                response_json, ok = _parse_json(raw)
                if not ok:
                    continue
            elif not (
                status == 204 and _looks_like_api_request(parts.path, had_json_body, request)
            ):
                continue
        else:
            continue

        error = error or request_error
        exchanges.append(
            Exchange(
                id=_exchange_id(index, method, url),
                method=method,
                url=url,
                path=parts.path,
                query=dict(reversed(parse_qsl(parts.query, keep_blank_values=True))),
                status=status,
                request_json=request_json,
                response_json=response_json,
                response_content_type=_media_type(content_type),
                error=error,
            )
        )

    return HarParseResult(
        exchanges=exchanges,
        expression=expression,
        documents=documents,
        dropped_media=dropped_media,
        out_of_scope=out_of_scope,
        dropped_assets=dropped_assets,
    )
