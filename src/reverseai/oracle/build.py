"""Build executable scenarios from observed exchanges and inferred endpoints."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlencode

from reverseai.observe.contracts import Endpoint, template_path
from reverseai.observe.har import Exchange
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.oracle.standalone import escape_token, is_volatile, json_equal

WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
ECHO_METHODS = frozenset({"POST", "PATCH", "PUT"})  # also: writes that chain by value
_ID_TEMPLATE = "{id}"
_MIN_SHARED_LEN = 3
_ENUM_LIKE_WRITES = (
    3  # a (key, value) sent by this many writes is an enum, not an identity
)

Producer = tuple[int, str]  # (exchange index, JSON pointer into its response)


def _is_id_key(key: str) -> bool:
    lowered = key.lower()
    return lowered == "id" or lowered.endswith("_id") or key.endswith("Id")


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _is_linkable(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, str) and len(value) >= 1)


def _find_producer(
    exchanges: list[Exchange], consumer: int, segment: str, templated: bool
) -> Producer | None:
    """Most recent earlier top-level response scalar equal to `segment`.

    Id-like keys (`id`, `*_id`, `*Id`) win over other keys, so a counter such as
    `{"done": 1}` never shadows an earlier `{"id": 1}`. Segments that are not path parameters
    per `template_path` are linked only from id-like keys, so literal segments such as
    `tasks` never link to an arbitrary string field.
    """
    passes = (True, False) if templated else (True,)
    for id_keys_only in passes:
        for index in range(consumer - 1, -1, -1):
            response = exchanges[index].response_json
            if not isinstance(response, dict):
                continue
            for key, value in response.items():
                if id_keys_only and not _is_id_key(key):
                    continue
                if _is_linkable(value) and str(value) == segment:
                    return index, "/" + escape_token(key)
    return None


def _constant_fields(
    exchanges: list[Exchange], templates: list[str]
) -> dict[tuple, dict]:
    """Per (method, template, status): top-level scalars identical in every example."""
    groups: dict[tuple, list[Any]] = defaultdict(list)
    for ex, template in zip(exchanges, templates, strict=True):
        groups[(ex.method, template, ex.status)].append(ex.response_json)

    constants: dict[tuple, dict] = {}
    for key, responses in groups.items():
        status = key[2]
        found: dict[str, Any] = {}
        if (len(responses) >= 2 or status >= 400) and all(
            isinstance(r, dict) for r in responses
        ):
            first = responses[0]
            for field, value in first.items():
                if (
                    _is_scalar(value)
                    and not is_volatile(value)
                    and not _is_id_key(field)
                    and all(
                        field in r and json_equal(r[field], value)
                        for r in responses[1:]
                    )
                ):
                    found["/" + escape_token(field)] = value
        constants[key] = found
    return constants


def _echo_fields(ex: Exchange) -> dict[str, Any]:
    request, response = ex.request_json, ex.response_json
    if ex.method not in ECHO_METHODS or not isinstance(request, dict):
        return {}
    if not isinstance(response, dict):
        return {}
    return {
        "/" + escape_token(field): value
        for field, value in response.items()
        if field in request
        and _is_scalar(value)
        and not is_volatile(value)
        and not _is_id_key(field)
        and json_equal(request[field], value)
    }


def _own_error_fields(ex: Exchange) -> dict[str, Any]:
    """For status >= 400: the response's own top-level non-volatile scalars (error codes)."""
    response = ex.response_json
    if ex.status < 400 or not isinstance(response, dict):
        return {}
    return {
        "/" + escape_token(field): value
        for field, value in response.items()
        if _is_scalar(value) and not is_volatile(value) and not _is_id_key(field)
    }


def _expected_values(
    ex: Exchange, template: str, constants: dict[tuple, dict]
) -> dict[str, Any]:
    equals = _echo_fields(ex)
    for source in (constants[(ex.method, template, ex.status)], _own_error_fields(ex)):
        for pointer, value in source.items():
            equals.setdefault(pointer, value)
    return equals


def _shared_request_values(ex: Exchange) -> set[tuple[str, str]]:
    """Top-level (key, string value) pairs of the request body usable for chaining."""
    body = ex.request_json
    if not isinstance(body, dict):
        return set()
    return {
        (k, v)
        for k, v in body.items()
        if isinstance(v, str) and len(v) >= _MIN_SHARED_LEN
    }


def _signature(ex: Exchange, template: str, equals: dict[str, Any]) -> tuple:
    body = ex.request_json
    body_keys: Any = (
        tuple(sorted(body)) if isinstance(body, dict) else type(body).__name__
    )
    return (
        ex.method,
        template,
        ex.status,
        body_keys,
        tuple(sorted(ex.query)),
        tuple(sorted(equals.items())),
    )


def build_scenarios(
    exchanges: list[Exchange], endpoints: list[Endpoint]
) -> list[Scenario]:
    """Turn observed API exchanges into (possibly chained) executable scenarios."""
    usable = [ex for ex in exchanges if ex.error is None and ex.status > 0]
    templates = [template_path(ex.path) for ex in usable]
    endpoint_by_key = {(ep.method, ep.path_template): ep for ep in endpoints}
    constants = _constant_fields(usable, templates)
    expected = [
        _expected_values(ex, t, constants)
        for ex, t in zip(usable, templates, strict=True)
    ]

    # Step 2: link path segments to earlier response values (union-find over exchanges).
    parent = list(range(len(usable)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    links: dict[int, dict[int, Producer]] = defaultdict(dict)
    for consumer, ex in enumerate(usable):
        template_segments = templates[consumer].split("/")
        for position, segment in enumerate(ex.path.split("/")):
            if not segment:
                continue
            templated = template_segments[position] == _ID_TEMPLATE
            producer = _find_producer(usable, consumer, segment, templated)
            if producer is not None:
                links[consumer][position] = producer
                parent[root(producer[0])] = root(consumer)

    # Chain by shared request values: a request that repeats a string (len >= 3) sent
    # under the same top-level key by an earlier write joins that write's scenario (e.g. a
    # 409 duplicate submit). Pairs sent by 3+ writes overall are enum-like (e.g. a
    # priority) and never chain. Bodies stay literal; no variables are involved.
    write_values = [
        _shared_request_values(ex) if ex.method in ECHO_METHODS else set()
        for ex in usable
    ]
    pair_writes = Counter(pair for values in write_values for pair in values)
    for index, ex in enumerate(usable):
        pairs = {
            p for p in _shared_request_values(ex) if pair_writes[p] < _ENUM_LIKE_WRITES
        }
        for earlier in range(index):
            if pairs & write_values[earlier]:
                parent[root(earlier)] = root(index)

    # Step 3: connected components, ordered by their first exchange.
    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(usable)):
        components[root(index)].append(index)

    scenarios: list[Scenario] = []
    seen: set[tuple] = set()
    for members in sorted(components.values(), key=lambda m: m[0]):
        signature = tuple(
            _signature(usable[i], templates[i], expected[i]) for i in members
        )
        if signature in seen:  # step 6: keep the first occurrence
            continue
        seen.add(signature)
        scenarios.append(
            _scenario(members, usable, templates, links, endpoint_by_key, expected)
        )

    for number, scenario in enumerate(scenarios, start=1):
        scenario.id = f"s{number:03d}"
    return scenarios


def _scenario(
    members: list[int],
    exchanges: list[Exchange],
    templates: list[str],
    links: dict[int, dict[int, Producer]],
    endpoint_by_key: dict[tuple[str, str], Endpoint],
    expected: list[dict[str, Any]],
) -> Scenario:
    names: dict[Producer, str] = {}
    for consumer in members:
        for _, producer in sorted(links[consumer].items()):
            names.setdefault(producer, f"v{len(names)}")

    steps: list[ScenarioStep] = []
    for index in members:
        ex = exchanges[index]
        segments = ex.path.split("/")
        for position, producer in links[index].items():
            segments[position] = "{" + names[producer] + "}"
        path = "/".join(segments)
        if ex.query:
            path += "?" + urlencode(ex.query)

        endpoint = endpoint_by_key.get((ex.method, templates[index]))
        schema = endpoint.response_schemas.get(ex.status) if endpoint else None
        steps.append(
            ScenarioStep(
                step=Step(
                    method=ex.method,
                    path=path,
                    json_body=ex.request_json,
                    save={name: p for (i, p), name in names.items() if i == index},
                ),
                expect=Expect(
                    status=ex.status,
                    json_shape=schema or None,
                    json_equals=expected[index],
                ),
            )
        )

    title = ", then ".join(
        f"{exchanges[i].method} {templates[i]} → {exchanges[i].status}" for i in members
    )
    critical = any(
        exchanges[i].method in WRITE_METHODS and 200 <= exchanges[i].status < 300
        for i in members
    )
    return Scenario(
        id="",
        title=title,
        steps=steps,
        critical=critical,
        source_exchanges=[exchanges[i].id for i in members],
    )
