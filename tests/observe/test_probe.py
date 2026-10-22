import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

from reverseai.bench.server import load_target, serve_asgi
from reverseai.observe.contracts import Endpoint, infer_endpoints
from reverseai.observe.har import MAX_BODY_BYTES, parse_har
from reverseai.observe.probe import probe_endpoints
from reverseai.project import Attestation, IntakeError, Mode, ProjectCard

taskboard = load_target("taskboard")
FIXTURE = Path(__file__).parent.parent / "fixtures" / "taskboard.har"


def make_card(base_url: str, *, sandbox: bool) -> ProjectCard:
    return ProjectCard(
        name="Demo",
        mode=Mode.LEGACY,
        target_base_url=base_url,
        allowed_domains=[urlparse(base_url).hostname or ""],
        target_is_sandbox=sandbox,
        attestation=Attestation(
            lawful_access=True, basis="own", signed_by="t", signed_at="2026-10-20T10:00:00Z"
        ),
        product_name="Acme Board",
    )


def no_sleep(_: float) -> None:
    pass


@pytest.fixture(scope="module")
def har_result():
    return parse_har(json.loads(FIXTURE.read_text()), ["127.0.0.1"])


@pytest.fixture
def taskboard_url():
    app = taskboard.create_app()
    with serve_asgi(app) as url:
        yield url


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def post_endpoint(schema: dict | None = None) -> Endpoint:
    schema = schema or {
        "type": "object",
        "properties": {"title": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["title"],
    }
    return Endpoint(
        method="POST",
        path_template="/api/items",
        statuses=[201],
        request_schema=schema,
        response_schemas={},
        exchange_ids=[],
    )


def test_probe_finds_validation_errors(taskboard_url, har_result):
    card = make_card(taskboard_url, sandbox=True)
    endpoints = infer_endpoints(har_result.exchanges)
    out = probe_endpoints(
        taskboard_url, endpoints, card, delay_s=0, exchanges=har_result.exchanges, sleep=no_sleep
    )
    assert any(
        e.status == 422 and isinstance(e.response_json, dict)
        and e.response_json["error"] == "title_required"
        for e in out
    )
    assert any(e.status == 404 and e.path == "/api/tasks/999999" for e in out)
    assert len({e.id for e in out}) == len(out)
    assert all(e.error is None for e in out)


def test_probe_patch_uses_observed_concrete_path(taskboard_url, har_result):
    card = make_card(taskboard_url, sandbox=True)
    patch = [e for e in infer_endpoints(har_result.exchanges) if e.method == "PATCH"]
    observed = next(e for e in har_result.exchanges if e.id == patch[0].exchange_ids[0])
    httpx.post(taskboard_url + "/api/tasks", json={"title": "x"}, trust_env=False)
    out = probe_endpoints(
        taskboard_url, patch, card, delay_s=0, exchanges=har_result.exchanges, sleep=no_sleep
    )
    paths = {e.path for e in out}
    assert observed.path in paths and "/api/tasks/999999" in paths
    assert any(e.path == observed.path and e.status == 422 for e in out)


def test_probe_unreachable_recorded(har_result):
    card = make_card("http://127.0.0.1:1", sandbox=True)
    endpoints = infer_endpoints(har_result.exchanges)
    out = probe_endpoints(
        "http://127.0.0.1:1", endpoints, card, delay_s=0, exchanges=har_result.exchanges,
        sleep=no_sleep,
    )
    assert out and all(e.error == "unreachable" and e.status == 0 for e in out)


def test_probe_requires_sandbox(har_result):
    card = make_card("http://127.0.0.1:1", sandbox=False)
    with pytest.raises(IntakeError):
        probe_endpoints("http://127.0.0.1:1", [], card, sleep=no_sleep)


def test_probe_rejects_base_url_outside_allowed_domains():
    card = make_card("http://127.0.0.1:1", sandbox=True)
    with pytest.raises(IntakeError):
        probe_endpoints("http://evil.example.org", [], card, sleep=no_sleep)


def test_probe_request_matrix():
    seen: list[tuple[str, str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        return httpx.Response(422, json={"error": "nope"})

    card = make_card("http://127.0.0.1:9", sandbox=True)
    with mock_client(handler) as client:
        out = probe_endpoints(
            "http://127.0.0.1:9", [post_endpoint()], card, client=client, delay_s=0, sleep=no_sleep
        )
    bodies = [b for _, _, b in seen]
    assert {} in bodies  # empty object
    assert any(isinstance(b, dict) and "title" not in b for b in bodies)  # required removed
    assert any(isinstance(b, dict) and b.get("title") == "x" * 201 for b in bodies)  # long string
    assert any(isinstance(b, dict) and b.get("title") == 12345 for b in bodies)  # wrong type
    assert any(isinstance(b, dict) and b.get("n") == "wrong_type" for b in bodies)
    assert all(e.response_json == {"error": "nope"} for e in out)
    assert all(m == "POST" and p == "/api/items" for m, p, _ in seen)


def test_probe_skips_validation_for_post_without_schema_or_get():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={})

    get = Endpoint(
        method="GET", path_template="/api/items", statuses=[200], request_schema=None,
        response_schemas={}, exchange_ids=[],
    )
    card = make_card("http://127.0.0.1:9", sandbox=True)
    with mock_client(handler) as client:
        out = probe_endpoints(
            "http://127.0.0.1:9", [get], card, client=client, delay_s=0, sleep=no_sleep
        )
    assert out == [] and seen == []


def test_probe_body_too_large_and_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.content == b"{}":
            return httpx.Response(
                200, content=b"x" * (MAX_BODY_BYTES + 1), headers={"content-type": "application/json"}
            )
        if b"title" not in request.content:
            return httpx.Response(200, content=b"<html>", headers={"content-type": "application/json"})
        return httpx.Response(200, content=b"plain", headers={"content-type": "text/plain"})

    card = make_card("http://127.0.0.1:9", sandbox=True)
    with mock_client(handler) as client:
        out = probe_endpoints(
            "http://127.0.0.1:9", [post_endpoint()], card, client=client, delay_s=0, sleep=no_sleep
        )
    assert out[0].error == "body_too_large" and out[0].response_json is None
    assert out[1].error == "invalid_json" and out[1].response_json is None
    plain = out[-1]
    assert plain.error is None and plain.response_json is None
    assert plain.response_content_type == "text/plain"


def test_probe_rate_limit_sleeps_between_requests():
    sleeps: list[float] = []
    card = make_card("http://127.0.0.1:9", sandbox=True)
    with mock_client(lambda r: httpx.Response(200, json={})) as client:
        out = probe_endpoints(
            "http://127.0.0.1:9", [post_endpoint()], card, client=client, delay_s=0.5,
            sleep=sleeps.append,
        )
    assert len(out) > 1
    assert sleeps == [0.5] * (len(out) - 1)


def test_probe_logs_to_ledger(tmp_path):
    from reverseai.provenance.ledger import Ledger

    ledger = Ledger(tmp_path / "ledger.jsonl")
    card = make_card("http://127.0.0.1:9", sandbox=True)
    with mock_client(lambda r: httpx.Response(200, json={})) as client:
        out = probe_endpoints(
            "http://127.0.0.1:9", [post_endpoint()], card, client=client, delay_s=0,
            sleep=no_sleep, ledger=ledger,
        )
    (event,) = [e for e in ledger.events() if e.type == "observe.probe"]
    assert (event.zone, event.actor, event.payload["count"]) == ("dirty", "observer", len(out))


def test_probe_id_template_only_not_found_probe():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(404, json={"error": "not_found"})

    delete = Endpoint(
        method="DELETE", path_template="/api/tasks/{id}", statuses=[204], request_schema=None,
        response_schemas={}, exchange_ids=[],
    )
    card = make_card("http://127.0.0.1:9", sandbox=True)
    with mock_client(handler) as client:
        out = probe_endpoints(
            "http://127.0.0.1:9", [delete], card, client=client, delay_s=0, sleep=no_sleep
        )
    assert seen == [("DELETE", "/api/tasks/999999")]
    assert out[0].status == 404
