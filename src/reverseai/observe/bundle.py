"""Observation bundle: everything the analyst LLM sees about the target, as one prompt."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from reverseai.observe.contracts import Endpoint
from reverseai.observe.explorer import FormInfo, PageObservation
from reverseai.observe.har import Exchange

_PAGE_TEXT_CHARS = 300
_MIN_DOCS_CHARS = 100
_TRUNCATION_MARK = "\n...[truncated]"


def _schema_str(schema: dict[str, Any]) -> str:
    """Compact one-line rendering of an inferred JSON schema."""
    declared = schema.get("type", "any")
    kind = "|".join(declared) if isinstance(declared, list) else str(declared)
    parts: list[str] = []
    properties = schema.get("properties")
    if properties is not None:
        required = set(schema.get("required", []))
        fields = ", ".join(
            f"{name}{'' if name in required else '?'}: {_schema_str(sub)}"
            for name, sub in properties.items()
        )
        parts.append("{" + fields + "}")
    if "items" in schema:
        parts.append("[" + _schema_str(schema["items"]) + "]")
    if "format" in schema:
        kind = f"{kind}({schema['format']})"
    if parts:
        rendered = " ".join(parts)
        return rendered if kind in ("object", "array") else f"{kind} {rendered}"
    return kind


def _form_str(form: FormInfo) -> str:
    fields = ", ".join(
        f"{f.name}:{f.type}{'*' if f.required else ''}" + (f" ({f.label})" if f.label else "")
        for f in form.fields
    )
    return f"{form.method} {form.action} [{fields}]"


def _page_lines(page: PageObservation, detail: bool) -> list[str]:
    head = f"- {page.url} \"{page.title}\""
    if not detail:
        return [head]
    lines = [head]
    lines += [f"  form: {_form_str(f)}" for f in page.forms]
    if page.buttons:
        lines.append("  buttons: " + ", ".join(page.buttons))
    if page.links:
        lines.append("  links: " + ", ".join(page.links))
    excerpt = " ".join(page.text_excerpt.split())[:_PAGE_TEXT_CHARS]
    if excerpt:
        lines.append(f"  text: {excerpt}")
    return lines


def _endpoint_lines(endpoint: Endpoint) -> list[str]:
    statuses = ",".join(str(s) for s in endpoint.statuses)
    lines = [f"{endpoint.method} {endpoint.path_template} (statuses: {statuses})"]
    if endpoint.request_schema:
        lines.append(f"  request: {_schema_str(endpoint.request_schema)}")
    for status, schema in sorted(endpoint.response_schemas.items()):
        if schema:
            lines.append(f"  response {status}: {_schema_str(schema)}")
    return lines


def _probe_line(ex: Exchange) -> str:
    code = ""
    if isinstance(ex.response_json, dict) and isinstance(ex.response_json.get("error"), str):
        code = ex.response_json["error"]
    code = code or ex.error or ""
    return f"{ex.method} {ex.path} -> {ex.status}" + (f" {code}" if code else "")


class ObservationBundle(BaseModel):
    pages: list[PageObservation]
    endpoints: list[Endpoint]
    probe_exchanges: list[Exchange]
    docs: list[str]

    def _render(self, *, page_detail: bool, probes: bool, docs: str | None) -> str:
        """`docs`: text to show under "# Docs" (None omits the section body)."""
        pages = [line for p in self.pages for line in _page_lines(p, page_detail)]
        endpoints = [line for e in self.endpoints for line in _endpoint_lines(e)]
        probe_lines = [_probe_line(e) for e in self.probe_exchanges] if probes else []
        sections = [
            ("# Pages", "\n".join(pages)),
            ("# Endpoints", "\n".join(endpoints)),
            ("# Probes", "\n".join(probe_lines)),
            ("# Docs", docs or ""),
        ]
        return "\n\n".join(f"{head}\n{body}".rstrip("\n") for head, body in sections) + "\n"

    def to_prompt(self, max_chars: int = 60_000) -> str:
        """Plain-text prompt with sections Pages, Endpoints, Probes, Docs; at most `max_chars`.

        When too long it degrades in order: docs are trimmed, then dropped; probes are dropped;
        page detail (forms, buttons, links, text) is dropped; finally the text is cut.
        """
        all_docs = "\n\n".join(self.docs)
        full = self._render(page_detail=True, probes=True, docs=all_docs)
        if len(full) <= max_chars:
            return full

        no_docs = self._render(page_detail=True, probes=True, docs=None)
        room = max_chars - len(no_docs) - len(_TRUNCATION_MARK)
        if room >= _MIN_DOCS_CHARS:
            return self._render(
                page_detail=True, probes=True, docs=all_docs[:room] + _TRUNCATION_MARK
            )[:max_chars]
        if len(no_docs) <= max_chars:
            return no_docs

        no_probes = self._render(page_detail=True, probes=False, docs=None)
        if len(no_probes) <= max_chars:
            return no_probes

        slim = self._render(page_detail=False, probes=False, docs=None)
        if len(slim) <= max_chars:
            return slim
        return slim[:max_chars]
