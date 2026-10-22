"""Sanitizer: strips the original's expression (code, verbatim text, brand, domains).

Prose (summary, titles, descriptions, evidence refs, gaps, entity field types, scenario titles)
goes through ``sanitize_text``: code, target domains, brand and verbatim spans. Identifiers
(spec item ids, entity names and field names, API paths, scenario step paths with their query,
request-body keys and string values) go through ``mask_identifier``: brand and target domains
only, reported like in prose. A path or key that also appears in the original is the interface
the clone must reproduce, so it is never rewritten into a removal marker; inside a URL path the
replacements are URL-safe. API methods, request/response schemas, ``json_equals`` pointers and
``save`` maps are kept as they are. Expected response values cross only under
``releasable_value``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Iterable, Iterator, Sequence
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel

from reverseai.oracle.model import Scenario
from reverseai.spec.model import BehaviorSpec

_TOKEN = re.compile(r"\w+|[^\w\s]")
_CODE_PATTERNS = [
    re.compile(p)
    for p in (r"function\s*\(", r"=>", r"\b(var|const|let)\s+\w+\s*=", r"\breturn\b.*;", r"\{\s*\}")
]
_SENTENCE_BREAK = re.compile(r"\. |\n")
_CODE_MARK = "[removed: code]"
_VERBATIM_MARK = "[removed: verbatim]"
_DOMAIN_MARK = "<original>"
_PATH_DOMAIN_MARK = "original"  # URL-safe stand-in for a target domain inside a path
_PATH_PRODUCT_FALLBACK = "product"
_EXCERPT_CHARS = 120
_IDENTIFIER = re.compile(r"[\w.:/-]{1,64}")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _token_offsets(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    """Tokens (as ``tokenize``) with their (start, end) character offsets in ``text``."""
    tokens: list[str] = []
    offsets: list[tuple[int, int]] = []
    for m in _TOKEN.finditer(text):
        tokens.append(m.group().lower())
        offsets.append(m.span())
    return tokens, offsets


class ExpressionIndex:
    """Set of token shingles of the original's expression (code, documents, page text)."""

    def __init__(self, shingle: int = 8) -> None:
        self.shingle = shingle
        self._hashes: set[int] = set()

    def add(self, text: str) -> None:
        tokens = tokenize(text)
        n = self.shingle
        self._hashes.update(hash(tuple(tokens[i : i + n])) for i in range(len(tokens) - n + 1))

    def contains_span(self, tokens: list[str]) -> list[tuple[int, int]]:
        """Token spans [start, end) covered by shingles of the index; overlapping runs merged."""
        n = self.shingle
        spans: list[tuple[int, int]] = []
        for i in range(len(tokens) - n + 1):
            if hash(tuple(tokens[i : i + n])) not in self._hashes:
                continue
            if spans and i <= spans[-1][1]:
                spans[-1] = (spans[-1][0], i + n)
            else:
                spans.append((i, i + n))
        return spans


def build_expression_index(texts: Iterable[str], shingle: int = 8) -> ExpressionIndex:
    index = ExpressionIndex(shingle)
    for text in texts:
        index.add(text)
    return index


class Finding(BaseModel):
    """What the sanitizer changed (or, for ``body_warning``, only flagged) and where.

    ``body_warning``: a request-body string value that matches the original's expression
    (verbatim span or code pattern). Body values are what the scenario sends, so they are
    kept as they are; the warning is for the human reviewer and never blocks a release.
    """

    kind: Literal["code", "verbatim", "brand", "url", "body_warning"]
    location: str
    excerpt: str


WARNING_KINDS = frozenset({"body_warning"})


def blocking(findings: Iterable[Finding]) -> list[Finding]:
    """The findings that make a draft unfit for release (everything but warnings)."""
    return [f for f in findings if f.kind not in WARNING_KINDS]


class SanitizeReport(BaseModel):
    findings: list[Finding]


def _excerpt(text: str) -> str:
    return text if len(text) <= _EXCERPT_CHARS else text[: _EXCERPT_CHARS - 1] + "…"


def _sentences(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _SENTENCE_BREAK.finditer(text):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(text)))
    return spans


def _remove_code(text: str, location: str) -> tuple[str, list[Finding]]:
    matches = [m.span() for p in _CODE_PATTERNS for m in p.finditer(text)]
    if not matches:
        return text, []
    sentences = _sentences(text)
    hit = [any(s < me and e > ms for ms, me in matches) for s, e in sentences]
    out: list[str] = []
    findings: list[Finding] = []
    i = 0
    while i < len(sentences):
        start, end = sentences[i]
        if hit[i]:
            j = i
            while j + 1 < len(sentences) and hit[j + 1]:
                j += 1
            end = sentences[j][1]
            raw = text[start:end]
            lead = len(raw) - len(raw.lstrip())
            tail = len(raw.rstrip())
            findings.append(Finding(kind="code", location=location, excerpt=_excerpt(raw.strip())))
            out.append(raw[:lead] + _CODE_MARK + raw[tail:])
            i = j
        else:
            out.append(text[start:end])
        if i + 1 < len(sentences):
            out.append(text[end : sentences[i + 1][0]])  # the separator
        i += 1
    return "".join(out), findings


def _domain_pattern(domains: Iterable[str], *, with_path: bool = True) -> re.Pattern[str] | None:
    """A target URL or bare domain; ``with_path=False`` stops at the host (and port)."""
    names = sorted({d.strip().lower() for d in domains if d.strip()}, key=len, reverse=True)
    if not names:
        return None
    hosts = "|".join(re.escape(d) for d in names)
    tail = r"""(?:[/?#](?:[^\s<>"']*[^\s<>"'.,;:!?)\]])?)?""" if with_path else ""
    return re.compile(
        r"(?<![\w.-])(?:[a-z][a-z0-9+.-]*://)?(?:[\w-]+\.)*"
        rf"(?:{hosts})(?![\w-])(?::\d+)?" + tail,
        re.IGNORECASE,
    )


def _origin_pattern(domains: Iterable[str]) -> re.Pattern[str] | None:
    """A target origin (``scheme://host[:port]``, ``//host`` or a bare host) opening a path."""
    names = sorted({d.strip().lower() for d in domains if d.strip()}, key=len, reverse=True)
    if not names:
        return None
    hosts = "|".join(re.escape(d) for d in names)
    return re.compile(
        rf"^(?:(?:[a-z][a-z0-9+.-]*:)?//)?(?:[\w-]+\.)*(?:{hosts})(?::\d+)?(?=[/?#]|$)",
        re.IGNORECASE,
    )


def _strip_origin(
    text: str, domains: Sequence[str], location: str
) -> tuple[str, list[Finding]]:
    """Drop a target origin that opens a path, keeping the path absolute.

    ``https://acme.com/api/x`` is the path ``/api/x`` of the target; the clone serves it at
    its own origin, so only the path crosses (the finding records the removed origin).
    """
    pattern = _origin_pattern(domains)
    m = pattern.match(text) if pattern is not None else None
    if m is None:
        return text, []
    rest = text[m.end() :]
    finding = Finding(kind="url", location=location, excerpt=_excerpt(m.group()))
    return (rest if rest.startswith("/") else "/" + rest), [finding]


def _camel_split(word: str) -> list[str]:
    """``TaskBoard`` → ``["Task", "Board"]``; letters and digits are separate parts too."""
    parts: list[str] = []
    for i, ch in enumerate(word):
        prev = word[i - 1] if i else ""
        split = bool(prev) and (
            (prev.islower() and ch.isupper()) or (prev.isdigit() != ch.isdigit())
        )
        if not parts or split:
            parts.append(ch)
        else:
            parts[-1] += ch
    return parts


def _brand_tokens(term: str) -> list[str]:
    return [part for word in re.findall(r"[^\W_]+", term) for part in _camel_split(word)]


# Between the words of a brand term: whitespace, ``_``, ``-``, ``+``, ``%20`` or nothing
# (``Task Board`` = ``TaskBoard`` = ``task_board`` = ``task-board`` = ``Task%20Board``).
_BRAND_GLUE = r"(?:\s+|[_+-]|%20)?"
_PERCENT_BYTE = re.compile(r"%[0-9A-Fa-f]{2}")


def _brand_pattern(brand_terms: Iterable[str]) -> re.Pattern[str] | None:
    """Every brand term, case-insensitive, its words joined by any ``_BRAND_GLUE``.

    Matches are only candidates: ``_brand_spans`` keeps those on identifier boundaries.
    """
    alts: list[str] = []
    for term in sorted({t.strip() for t in brand_terms if t.strip()}, key=len, reverse=True):
        tokens = _brand_tokens(term)
        if tokens:
            alts.append(_BRAND_GLUE.join(re.escape(t) for t in tokens))
    if not alts:
        return None
    return re.compile("|".join(f"(?:{a})" for a in alts), re.IGNORECASE)


def _left_boundary(text: str, start: int) -> bool:
    """A brand may start here: string start, after a non-alphanumeric, a percent-encoded byte,
    or a camelCase hump (``myAcme``)."""
    if start == 0:
        return True
    prev, first = text[start - 1], text[start]
    if not prev.isalnum():
        return True
    if start >= 3 and _PERCENT_BYTE.fullmatch(text[start - 3 : start]):
        return True
    return first.isupper() and (prev.islower() or prev.isdigit())


def _right_boundary(text: str, end: int) -> bool:
    """A brand may end here: string end, before a non-alphanumeric, a digit or a camelCase hump
    (``AcmeTasks``)."""
    if end == len(text):
        return True
    nxt, last = text[end], text[end - 1]
    if not nxt.isalnum() or nxt.isdigit():
        return True
    return nxt.isupper() and not last.isupper()


def _brand_spans(text: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    """Non-overlapping brand occurrences on identifier boundaries, left to right."""
    spans: list[tuple[int, int]] = []
    pos = 0
    while (m := pattern.search(text, pos)) is not None:
        start, end = m.span()
        if end > start and _left_boundary(text, start) and _right_boundary(text, end):
            spans.append((start, end))
            pos = end
        else:
            pos = start + 1
    return spans


def has_brand(text: str, brand_terms: Iterable[str]) -> bool:
    """Whether ``text`` mentions a brand term under the barrier's rule (also glued inside
    identifiers); the audit uses it so it flags exactly what the barrier would mask."""
    pattern = _brand_pattern(brand_terms)
    return pattern is not None and bool(_brand_spans(text, pattern))


def _glued(text: str, start: int, end: int) -> bool:
    """The brand is part of a longer identifier (``acme_id``, ``AcmeTasks``, ``my-acme``)."""

    def joins(ch: str) -> bool:
        return ch.isalnum() or ch in "_-"

    left = start > 0 and joins(text[start - 1])
    if left and start >= 3 and _PERCENT_BYTE.fullmatch(text[start - 3 : start]):
        left = False  # an encoded space or slash, not glue
    return left or (end < len(text) and joins(text[end]))


def _compact(name: str) -> str:
    return "".join(ch for ch in name if ch.isalnum()) or _PATH_PRODUCT_FALLBACK


def _same_case(replacement: str, matched: str) -> str:
    """``replacement`` in the letter case of ``matched`` (lower, UPPER, or first letter)."""
    letters = [ch for ch in matched if ch.isalpha()]
    if letters and all(ch.islower() for ch in letters):
        return replacement.lower()
    if len(letters) > 1 and all(ch.isupper() for ch in letters):
        return replacement.upper()
    head = replacement[0].upper() if matched[:1].isupper() else replacement[0].lower()
    return head + replacement[1:]


def _mask_brand(
    text: str,
    brand_terms: Iterable[str],
    product_name: str,
    location: str,
    *,
    url_path: bool = False,
) -> tuple[str, list[Finding]]:
    """Replace every brand occurrence, also inside identifiers (``acme_id``, ``AcmeTasks``).

    A standalone brand becomes the product name (``path_slug`` of it in a URL path); a brand
    glued into a longer identifier becomes the product name without spaces or punctuation, in
    the brand's letter case, so the identifier stays one identifier (ASCII only in a path).
    """
    pattern = _brand_pattern(brand_terms)
    if pattern is None:
        return text, []
    spans = _brand_spans(text, pattern)
    if not spans:
        return text, []
    standalone = path_slug(product_name) if url_path else product_name
    compact = path_slug(product_name).replace("-", "") if url_path else _compact(product_name)
    findings: list[Finding] = []
    out: list[str] = []
    pos = 0
    for start, end in spans:
        matched = text[start:end]
        findings.append(Finding(kind="brand", location=location, excerpt=_excerpt(matched)))
        repl = _same_case(compact, matched) if _glued(text, start, end) else standalone
        out += [text[pos:start], _keep_newline(matched, repl)]
        pos = end
    out.append(text[pos:])
    return "".join(out), findings


def _replace(
    text: str, pattern: re.Pattern[str] | None, repl: str, kind: str, location: str
) -> tuple[str, list[Finding]]:
    if pattern is None:
        return text, []
    findings: list[Finding] = []

    def sub(m: re.Match[str]) -> str:
        findings.append(Finding(kind=kind, location=location, excerpt=_excerpt(m.group())))
        return _keep_newline(m.group(), repl)

    return pattern.sub(sub, text), findings


def _keep_newline(removed: str, repl: str) -> str:
    """Keep a line break that the removed span contained.

    Joining two lines would let a later pass see a new code match (``.*`` stops at newlines),
    which would make the sanitizer non-idempotent.
    """
    return repl + "\n" if "\n" in removed else repl


def mask_identity(
    text: str, *, brand_terms: list[str], product_name: str, target_domains: list[str]
) -> str:
    """Apply the domain and brand replacements of ``sanitize_text`` without reporting them.

    Used on index texts so copy around brand names or URLs still matches sanitized prose.
    """
    text, _ = _replace(text, _domain_pattern(target_domains), _DOMAIN_MARK, "url", "")
    text, _ = _mask_brand(text, brand_terms, product_name, "")
    return text


def path_slug(name: str) -> str:
    """URL-safe form of a product name for use inside a path segment ("My App" → "my-app")."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or _PATH_PRODUCT_FALLBACK


def mask_identifier(
    text: str,
    *,
    location: str,
    brand_terms: Sequence[str],
    product_name: str,
    target_domains: Sequence[str],
    url_path: bool = False,
) -> tuple[str, list[Finding]]:
    """Mask brand and target domains in an identifier, with findings; nothing else changes.

    No verbatim or code pass: an API path, id or key that also appears in the original's
    pages or responses is the interface to reproduce, not copied expression. With
    ``url_path`` the replacements are URL-safe (host only → "original", brand → slug).
    """
    if url_path:
        text, origin = _strip_origin(text, target_domains, location)
        domains = _domain_pattern(target_domains, with_path=False)
        text, urls = _replace(text, domains, _PATH_DOMAIN_MARK, "url", location)
        urls = origin + urls
    else:
        text, urls = _replace(text, _domain_pattern(target_domains), _DOMAIN_MARK, "url", location)
    text, brands = _mask_brand(text, brand_terms, product_name, location, url_path=url_path)
    return text, urls + brands


def _remove_verbatim(
    text: str, index: ExpressionIndex, location: str
) -> tuple[str, list[Finding]]:
    tokens, offsets = _token_offsets(text)
    spans = index.contains_span(tokens)
    findings: list[Finding] = []
    for start_tok, end_tok in reversed(spans):
        start, end = offsets[start_tok][0], offsets[end_tok - 1][1]
        findings.append(
            Finding(kind="verbatim", location=location, excerpt=_excerpt(text[start:end]))
        )
        text = text[:start] + _keep_newline(text[start:end], _VERBATIM_MARK) + text[end:]
    findings.reverse()
    return text, findings


def body_warnings(text: str, index: ExpressionIndex, location: str) -> list[Finding]:
    """``body_warning`` findings for a request-body value with code or verbatim spans."""
    _, code = _remove_code(text, location)
    _, verbatim = _remove_verbatim(text, index, location)
    return [
        Finding(kind="body_warning", location=location, excerpt=f"{f.kind}: {f.excerpt}")
        for f in code + verbatim
    ]


def sanitize_text(
    text: str,
    *,
    location: str,
    index: ExpressionIndex,
    brand_terms: list[str],
    product_name: str,
    target_domains: list[str],
) -> tuple[str, list[Finding]]:
    """Rewrite one prose string.

    Order: code, target URLs/domains, brand, verbatim spans, then code once more so the
    result is a fixed point (a second run yields no findings).
    """
    text, code = _remove_code(text, location)
    text, urls = _replace(text, _domain_pattern(target_domains), _DOMAIN_MARK, "url", location)
    text, brands = _mask_brand(text, brand_terms, product_name, location)
    text, verbatim = _remove_verbatim(text, index, location)
    text, late_code = _remove_code(text, location)
    return text, code + urls + brands + verbatim + late_code


# --- JSON keys: one rename per key for the whole package ---------------------------------


def _escape_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _pointer_tokens(pointer: str) -> list[str]:
    """RFC 6901 tokens of ``pointer`` (none for ``""`` or a malformed pointer)."""
    if not pointer.startswith("/"):
        return []
    return [_unescape_token(token) for token in pointer[1:].split("/")]


class KeyRenames:
    """Masked names for JSON keys: body keys, schema properties, pointer tokens, entity fields.

    One instance covers a whole package, so a key renamed in a request body is renamed the
    same way in schemas, ``json_equals`` pointers, ``save`` maps and entity fields, and the
    clone never sees two names for one field. A masked key that collides with another name
    gets the first free ``_2``, ``_3``… suffix, so two keys never merge. Keys first seen
    after construction are masked on demand under the same rule.
    """

    def __init__(self, keys: Iterable[str], mask: Callable[[str], str]) -> None:
        self._mask = mask
        self._map: dict[str, str] = {}
        self._taken: set[str] = set()
        unique = sorted(set(keys))
        masked = {key: mask(key) for key in unique}
        self._taken = {key for key in unique if masked[key] == key}
        for key in unique:
            self._assign(key, masked[key])

    def _assign(self, key: str, masked: str) -> str:
        if masked == key:
            self._taken.add(key)
            self._map[key] = key
            return key
        name, n = masked, 2
        while name in self._taken:
            name = f"{masked}_{n}"
            n += 1
        self._taken.add(name)
        self._map[key] = name
        return name

    def __call__(self, key: str) -> str:
        if key in self._map:
            return self._map[key]
        return self._assign(key, self._mask(key))

    def pointer(self, pointer: str) -> str:
        tokens = _pointer_tokens(pointer)
        if not tokens:
            return pointer
        return "/" + "/".join(_escape_token(self(token)) for token in tokens)


def _schema_keys(schema: Any) -> Iterator[str]:
    """Property names (and ``required`` entries) of an inferred JSON schema, recursively."""
    if not isinstance(schema, dict):
        return
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, sub in properties.items():
            yield str(name)
            yield from _schema_keys(sub)
    required = schema.get("required")
    if isinstance(required, list):
        yield from (name for name in required if isinstance(name, str))
    if "items" in schema:
        yield from _schema_keys(schema["items"])


def _json_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _json_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _json_keys(item)


def _package_keys(spec: BehaviorSpec | None, scenarios: Iterable[Scenario]) -> Iterator[str]:
    if spec is not None:
        for entity in spec.entities:
            yield from entity.fields
        for contract in spec.api:
            yield from _schema_keys(contract.request_schema)
            for schema in contract.responses.values():
                yield from _schema_keys(schema)
    for scenario in scenarios:
        for scenario_step in scenario.steps:
            step, expect = scenario_step.step, scenario_step.expect
            yield from _json_keys(step.json_body)
            for pointer in step.save.values():
                yield from _pointer_tokens(pointer)
            for pointer in expect.json_equals:
                yield from _pointer_tokens(pointer)
            yield from _schema_keys(expect.json_shape)


def key_renames(
    spec: BehaviorSpec | None,
    scenarios: Iterable[Scenario],
    *,
    brand_terms: Sequence[str],
    product_name: str,
    target_domains: Sequence[str],
) -> KeyRenames:
    """The package-wide ``KeyRenames`` over every key the spec and scenarios name."""

    def mask(key: str) -> str:
        return mask_identifier(
            key,
            location="",
            brand_terms=brand_terms,
            product_name=product_name,
            target_domains=target_domains,
        )[0]

    return KeyRenames(_package_keys(spec, list(scenarios)), mask)


def _rename_schema(schema: Any, renames: KeyRenames, report: Callable[[str], None]) -> Any:
    """``schema`` with property names and ``required`` entries renamed; ``report`` gets each
    renamed original key."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            properties: dict[str, Any] = {}
            for name, sub in value.items():
                new = renames(str(name))
                if new != name:
                    report(str(name))
                properties[new] = _rename_schema(sub, renames, report)
            out[key] = properties
        elif key == "required" and isinstance(value, list):
            out[key] = [renames(name) if isinstance(name, str) else name for name in value]
        elif key == "items":
            out[key] = _rename_schema(value, renames, report)
        else:
            out[key] = value
    return out


def sanitize_spec(
    spec: BehaviorSpec,
    index: ExpressionIndex,
    *,
    brand_terms: list[str],
    target_domains: list[str],
    renames: KeyRenames | None = None,
) -> tuple[BehaviorSpec, SanitizeReport]:
    """Sanitize every string field of the spec: prose fully, ids, names and paths by masking.

    Methods are kept. Entity field names and the property names of request/response schemas
    are renamed by ``renames`` (built over the spec alone when not given; pass the package's
    to share names with the scenarios), so masked names that collide get ``_2``, ``_3``….
    """
    findings: list[Finding] = []
    if renames is None:
        renames = key_renames(
            spec, [], brand_terms=brand_terms, product_name=spec.product_name,
            target_domains=target_domains,
        )

    def mask(text: str, location: str, *, url_path: bool = False) -> str:
        out, found = mask_identifier(
            text,
            location=location,
            brand_terms=brand_terms,
            product_name=spec.product_name,
            target_domains=target_domains,
            url_path=url_path,
        )
        findings.extend(found)
        return out

    def clean(text: str, location: str) -> str:
        out, found = sanitize_text(
            text,
            location=location,
            index=index,
            brand_terms=brand_terms,
            product_name=spec.product_name,
            target_domains=target_domains,
        )
        findings.extend(found)
        return out

    def schema(value: Any, location: str) -> Any:
        return _rename_schema(value, renames, lambda key: mask(key, location))

    result = spec.model_copy(deep=True)
    result.summary = clean(result.summary, "summary")
    for section in ("features", "rules"):
        for i, item in enumerate(getattr(result, section)):
            loc = f"{section}[{i}]"
            item.id = mask(item.id, f"{loc}.id")
            item.title = clean(item.title, f"{loc}.title")
            item.description = clean(item.description, f"{loc}.description")
            for j, evidence in enumerate(item.evidence):
                evidence.ref = clean(evidence.ref, f"{loc}.evidence[{j}].ref")
    for i, entity in enumerate(result.entities):
        entity.name = mask(entity.name, f"entities[{i}].name")
        fields: dict[str, str] = {}
        for key, value in entity.fields.items():
            name = renames(key)
            if name != key:
                mask(key, f"entities[{i}].fields.key")
            fields[name] = clean(value, f"entities[{i}].fields[{name}]")
        entity.fields = fields
        entity.description = clean(entity.description, f"entities[{i}].description")
    for i, contract in enumerate(result.api):
        contract.path = mask(contract.path, f"api[{i}].path", url_path=True)
        contract.request_schema = schema(contract.request_schema, f"api[{i}].request_schema")
        contract.responses = {
            status: schema(value, f"api[{i}].responses[{status}]")
            for status, value in contract.responses.items()
        }
        contract.description = clean(contract.description, f"api[{i}].description")
    result.gaps = [clean(gap, f"gaps[{i}]") for i, gap in enumerate(result.gaps)]
    return result, SanitizeReport(findings=findings)


def json_strings(value: Any) -> Iterator[str]:
    """Every string inside a JSON document: values and dict keys."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from json_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from json_strings(item)


def _folded(text: str) -> str:
    """Whitespace-collapsed, case-folded form: a server's trim/lowercase of what it was sent."""
    return " ".join(text.split()).casefold()


def request_values(scenario: Scenario) -> set[str]:
    """What the scenario itself sends: body strings, paths, path segments and query values."""
    values: set[str] = set()
    for scenario_step in scenario.steps:
        step = scenario_step.step
        values.update(json_strings(step.json_body))
        values.add(step.path)
        parts = urlsplit(step.path)
        values.update(segment for segment in parts.path.split("/") if segment)
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            values.update((key, value))
    return values


def releasable_value(
    value: Any,
    *,
    request_values: Collection[str] = (),
    index: ExpressionIndex,
    brand_terms: Sequence[str],
    product_name: str,
    target_domains: Sequence[str],
) -> bool:
    """The one rule for an expected value crossing to the clean zone (release and feedback).

    Numbers, booleans and null cross. A string crosses only when it is sanitizer-clean and either
    identifier-like (up to 64 word characters or ``.:/-``, no spaces) or a value the scenario
    itself sent (``request_values``, compared after collapsing whitespace and case, so a trimmed
    or lower-cased echo counts). Anything else, prose and containers included, is withheld.
    """
    if value is None or isinstance(value, bool | int | float):
        return True
    if not isinstance(value, str):
        return False
    sent = value in request_values or _folded(value) in {_folded(v) for v in request_values}
    if not (_IDENTIFIER.fullmatch(value) or sent):
        return False
    _, findings = sanitize_text(
        value,
        location="value",
        index=index,
        brand_terms=list(brand_terms),
        product_name=product_name,
        target_domains=list(target_domains),
    )
    return not findings


def _sanitize_json(
    value: Any, clean: Callable[[str], str], rename: Callable[[str], str]
) -> Any:
    """``clean`` applied to every string value of a JSON document, ``rename`` to every key."""
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, dict):
        return {rename(str(key)): _sanitize_json(item, clean, rename) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item, clean, rename) for item in value]
    return value


def _same_json(a: Any, b: Any) -> bool:
    """JSON equality that never treats booleans as numbers."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def withheld_expectations(original: Scenario, released: Scenario) -> list[tuple[int, str]]:
    """(step index, JSON pointer of ``original``) of every expected value the release dropped.

    The release keeps a step's expectations in order, with values unchanged and pointers
    possibly renamed (``KeyRenames``), and whether a value is kept depends only on the value.
    So the kept ones are matched in order, by pointer or else by value; the rest were dropped.
    """
    dropped: list[tuple[int, str]] = []
    for i, (before, after) in enumerate(zip(original.steps, released.steps, strict=False)):
        kept = list(after.expect.json_equals.items())
        j = 0
        for pointer, value in before.expect.json_equals.items():
            if j < len(kept) and (kept[j][0] == pointer or _same_json(kept[j][1], value)):
                j += 1
            else:
                dropped.append((i, pointer))
    return dropped


def sanitize_scenarios(
    scenarios: list[Scenario],
    index: ExpressionIndex,
    *,
    brand_terms: Sequence[str] = (),
    product_name: str = "",
    target_domains: Sequence[str] = (),
    renames: KeyRenames | None = None,
) -> tuple[list[Scenario], list[Finding]]:
    """``release_scenarios`` plus the findings from titles, step paths and request bodies.

    Request-body string values are masked like identifiers; a value that also matches the
    original's expression is kept and reported as a non-blocking ``body_warning``.

    Request-body keys, ``save`` and ``json_equals`` pointers and ``json_shape`` property names
    are renamed by ``renames`` (built over these scenarios when not given).
    """
    if renames is None:
        renames = key_renames(
            None, scenarios, brand_terms=brand_terms, product_name=product_name,
            target_domains=target_domains,
        )

    def check(text: str, location: str) -> tuple[str, list[Finding]]:
        return sanitize_text(
            text,
            location=location,
            index=index,
            brand_terms=list(brand_terms),
            product_name=product_name,
            target_domains=list(target_domains),
        )

    def mask(text: str, location: str, *, url_path: bool = False) -> tuple[str, list[Finding]]:
        return mask_identifier(
            text,
            location=location,
            brand_terms=brand_terms,
            product_name=product_name,
            target_domains=target_domains,
            url_path=url_path,
        )

    findings: list[Finding] = []

    def body_value(text: str, location: str) -> str:
        out_text, found = mask(text, location)
        findings.extend(found)
        findings.extend(body_warnings(out_text, index, location))  # flagged, kept as sent
        return out_text

    def renamed(key: str, location: str) -> str:
        name = renames(key)
        if name != key:
            findings.extend(mask(key, location)[1])
        return name

    def pointer(value: str, location: str) -> str:
        for token in _pointer_tokens(value):
            renamed(token, location)
        return renames.pointer(value)

    released: list[Scenario] = []
    for scenario in scenarios:
        out = scenario.model_copy(deep=True)
        out.title, found = check(out.title, f"scenarios[{scenario.id}].title")
        findings.extend(found)
        out.source_exchanges = []
        for i, s in enumerate(out.steps):
            loc = f"scenarios[{scenario.id}].steps[{i}]"
            step, expect = s.step, s.expect
            step.path, found = mask(step.path, f"{loc}.path", url_path=True)
            findings.extend(found)
            body = f"{loc}.json_body"
            step.json_body = _sanitize_json(
                step.json_body, lambda text, b=body: body_value(text, b),
                lambda key, b=body: renamed(key, b),
            )
            step.save = {
                name: pointer(value, f"{loc}.save") for name, value in step.save.items()
            }
            expect.json_equals = {
                pointer(key, f"{loc}.expect.json_equals"): value
                for key, value in expect.json_equals.items()
            }
            shape = f"{loc}.expect.json_shape"
            expect.json_shape = _rename_schema(
                expect.json_shape, renames, lambda key, sh=shape: renamed(key, sh)
            )
        sent = request_values(out)
        for s in out.steps:
            s.expect.json_equals = {
                key: value
                for key, value in s.expect.json_equals.items()
                if releasable_value(
                    value,
                    request_values=sent,
                    index=index,
                    brand_terms=brand_terms,
                    product_name=product_name,
                    target_domains=target_domains,
                )
            }
        released.append(out)
    return released, findings


def release_scenarios(
    scenarios: list[Scenario],
    index: ExpressionIndex,
    *,
    brand_terms: Sequence[str] = (),
    product_name: str = "",
    target_domains: Sequence[str] = (),
) -> list[Scenario]:
    """Scenarios fit for the clean zone.

    Keeps steps, statuses and shapes (paths and bodies masked, keys renamed); keeps an exact
    expected value only if ``releasable_value`` allows it; drops links to dirty-zone exchanges.
    """
    released, _ = sanitize_scenarios(
        scenarios,
        index,
        brand_terms=brand_terms,
        product_name=product_name,
        target_domains=target_domains,
    )
    return released
