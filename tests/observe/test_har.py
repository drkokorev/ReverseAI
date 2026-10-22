import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from reverseai.observe.har import (
    MAX_BODY_BYTES,
    MAX_EXPRESSION_BYTES,
    AssetClass,
    HarParseResult,
    classify,
    parse_har,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "taskboard.har"
ALLOWED = ["127.0.0.1"]


def make_entry(
    method: str = "GET",
    url: str = "http://127.0.0.1:8000/api/x",
    status: int = 200,
    content_type: str | None = "application/json",
    text: str | None = "{}",
    encoding: str | None = None,
    post_text: str | None = None,
    post_mime: str | None = "application/json",
    request_headers: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {"method": method, "url": url, "headers": request_headers or []}
    if post_text is not None:
        request["postData"] = {"mimeType": post_mime, "text": post_text}
    content: dict[str, Any] = {"size": len(text or ""), "mimeType": content_type or ""}
    if text is not None:
        content["text"] = text
    if encoding:
        content["encoding"] = encoding
    headers = [{"name": "Content-Type", "value": content_type}] if content_type else []
    return {
        "request": request,
        "response": {"status": status, "headers": headers, "content": content},
    }


def har_of(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"log": {"version": "1.2", "entries": list(entries)}}


@pytest.fixture(scope="module")
def taskboard() -> HarParseResult:
    return parse_har(json.loads(FIXTURE.read_text()), ALLOWED)


def test_classify() -> None:
    assert classify("application/javascript", "/static/app.js") == AssetClass.EXPRESSION
    assert classify("text/css; charset=utf-8", "/s.css") == AssetClass.EXPRESSION
    assert classify("application/wasm", "/m.wasm") == AssetClass.EXPRESSION
    assert classify("application/json", "/static/app.js.map") == AssetClass.EXPRESSION
    assert classify("", "/static/app.js") == AssetClass.EXPRESSION
    assert classify("image/png", "/a.png") == AssetClass.MEDIA
    assert classify("font/woff2", "/f.woff2") == AssetClass.MEDIA
    assert classify("audio/mpeg", "/a.mp3") == AssetClass.MEDIA
    assert classify("video/mp4", "/v.mp4") == AssetClass.MEDIA
    assert classify("text/html; charset=utf-8", "/") == AssetClass.DOCUMENT
    assert classify("application/json", "/api/tasks") == AssetClass.API
    assert classify("application/problem+json", "/api/tasks") == AssetClass.API
    assert classify("text/plain", "/robots.txt") == AssetClass.OTHER
    assert classify("", "/api/tasks") == AssetClass.OTHER


def test_asset_class_values_are_lowercase() -> None:
    assert {c.value for c in AssetClass} == {"api", "document", "expression", "media", "other"}


def test_fixture_buckets(taskboard: HarParseResult) -> None:
    assert [d.url for d in taskboard.documents] == ["http://127.0.0.1:8000/"]
    assert "<title>TaskBoard Pro</title>" in taskboard.documents[0].content
    assert [e.url for e in taskboard.expression] == ["http://127.0.0.1:8000/static/app.js"]
    assert taskboard.dropped_media == 1
    assert taskboard.out_of_scope == 1
    assert len(taskboard.exchanges) == 11


def test_fixture_exchanges(taskboard: HarParseResult) -> None:
    created = taskboard.exchanges[1]
    assert (created.method, created.path, created.status) == ("POST", "/api/tasks", 201)
    assert created.request_json == {"title": "Write report", "priority": "high"}
    assert created.response_json["id"] == 1
    assert created.response_content_type == "application/json"
    assert created.error is None
    base64_body = next(e for e in taskboard.exchanges if e.path == "/api/tasks/2")
    assert base64_body.response_json["title"] == "Buy milk"
    deleted = next(e for e in taskboard.exchanges if e.method == "DELETE")
    assert deleted.status == 204
    assert deleted.response_json is None
    assert deleted.error is None


def test_out_of_scope_dropped() -> None:
    har = har_of(
        make_entry(url="https://cdn.example.org/api/x"),
        make_entry(url="http://127.0.0.1:8000/api/x"),
        make_entry(url="http://EVIL.127.0.0.1.example/api/x"),
    )
    result = parse_har(har, ["127.0.0.1"])
    assert result.out_of_scope == 2
    assert len(result.exchanges) == 1


def test_domain_match_is_case_insensitive_and_ignores_port() -> None:
    har = har_of(make_entry(url="https://API.Example.com:8443/v1/x"))
    result = parse_har(har, ["Api.example.COM"])
    assert result.out_of_scope == 0
    assert len(result.exchanges) == 1


def test_large_body_capped() -> None:
    big = json.dumps({"blob": "x" * MAX_BODY_BYTES})
    result = parse_har(har_of(make_entry(text=big)), ALLOWED)
    (ex,) = result.exchanges
    assert ex.error == "body_too_large"
    assert ex.response_json is None


def test_large_body_checked_after_base64_decoding() -> None:
    raw = json.dumps({"blob": "x" * MAX_BODY_BYTES}).encode()
    encoded = base64.b64encode(raw).decode()
    (ex,) = parse_har(har_of(make_entry(text=encoded, encoding="base64")), ALLOWED).exchanges
    assert ex.error == "body_too_large"
    small = base64.b64encode(b'{"ok": true}').decode()
    (ok,) = parse_har(har_of(make_entry(text=small, encoding="base64")), ALLOWED).exchanges
    assert ok.error is None
    assert ok.response_json == {"ok": True}


def test_large_request_body_capped() -> None:
    big = json.dumps({"blob": "x" * MAX_BODY_BYTES})
    (ex,) = parse_har(har_of(make_entry(method="POST", post_text=big)), ALLOWED).exchanges
    assert ex.error == "body_too_large"
    assert ex.request_json is None


def test_invalid_json_with_json_content_type() -> None:
    (ex,) = parse_har(har_of(make_entry(text="<html>oops</html>")), ALLOWED).exchanges
    assert ex.error == "invalid_json"
    assert ex.response_json is None
    assert ex.status == 200


def test_unparsable_base64_body_is_invalid_json() -> None:
    (ex,) = parse_har(har_of(make_entry(text="!!!not base64!!!", encoding="base64")), ALLOWED).exchanges
    assert ex.error == "invalid_json"


def test_non_json_request_body_is_not_an_error() -> None:
    entry = make_entry(method="POST", post_text="a=1&b=2", post_mime="application/x-www-form-urlencoded")
    (ex,) = parse_har(har_of(entry), ALLOWED).exchanges
    assert ex.request_json is None
    assert ex.error is None
    broken = make_entry(method="POST", post_text="{not json")
    (ex,) = parse_har(har_of(broken), ALLOWED).exchanges
    assert ex.request_json is None
    assert ex.error is None


def test_request_json_detected_from_header_when_post_mime_missing() -> None:
    entry = make_entry(
        method="POST",
        post_text='{"a": 1}',
        post_mime=None,
        request_headers=[{"name": "content-type", "value": "application/json; charset=utf-8"}],
    )
    (ex,) = parse_har(har_of(entry), ALLOWED).exchanges
    assert ex.request_json == {"a": 1}


def test_missing_content_type_with_json_body_counts_as_api() -> None:
    entry = make_entry(content_type=None, text='{"a": 1}')
    (ex,) = parse_har(har_of(entry), ALLOWED).exchanges
    assert ex.response_json == {"a": 1}
    assert ex.response_content_type == ""
    plain = make_entry(url="http://127.0.0.1:8000/readme", content_type=None, text="hello")
    result = parse_har(har_of(plain), ALLOWED)
    assert result.exchanges == []


def test_204_empty_body_counts_only_for_api_requests() -> None:
    api_path = make_entry(method="DELETE", url="http://127.0.0.1:8000/api/t/1", status=204, content_type=None, text="")
    (ex,) = parse_har(har_of(api_path), ALLOWED).exchanges
    assert ex.status == 204 and ex.response_json is None and ex.error is None

    with_json_req = make_entry(
        method="PUT", url="http://127.0.0.1:8000/t/1", status=204, content_type=None, text=None, post_text="{}"
    )
    assert len(parse_har(har_of(with_json_req), ALLOWED).exchanges) == 1

    accept_json = make_entry(
        url="http://127.0.0.1:8000/t/1",
        status=204,
        content_type=None,
        text=None,
        request_headers=[{"name": "Accept", "value": "application/json, */*"}],
    )
    assert len(parse_har(har_of(accept_json), ALLOWED).exchanges) == 1

    not_api = make_entry(method="GET", url="http://127.0.0.1:8000/ping", status=204, content_type=None, text="")
    assert parse_har(har_of(not_api), ALLOWED).exchanges == []


def test_exchange_id_and_query() -> None:
    url = "http://127.0.0.1:8000/api/tasks?done=1&q=a%20b"
    har = har_of(make_entry(url="https://cdn.example.org/x"), make_entry(url=url))
    (ex,) = parse_har(har, ALLOWED).exchanges
    assert ex.id == hashlib.sha256(f"1:GET:{url}".encode()).hexdigest()[:12]
    assert ex.path == "/api/tasks"
    assert ex.query == {"done": "1", "q": "a b"}


def test_other_assets_are_ignored() -> None:
    entry = make_entry(url="http://127.0.0.1:8000/robots.txt", content_type="text/plain", text="User-agent: *")
    result = parse_har(har_of(entry), ALLOWED)
    assert result.exchanges == [] and result.expression == [] and result.documents == []
    assert result.dropped_media == 0 and result.out_of_scope == 0


def test_base64_expression_is_decoded() -> None:
    body = base64.b64encode("var a = 'é';".encode()).decode()
    entry = make_entry(
        url="http://127.0.0.1:8000/a.js", content_type="application/javascript", text=body, encoding="base64"
    )
    (asset,) = parse_har(har_of(entry), ALLOWED).expression
    assert asset.content == "var a = 'é';"


def test_empty_har() -> None:
    result = parse_har({"log": {"entries": []}}, ALLOWED)
    assert result == HarParseResult(
        exchanges=[], expression=[], documents=[], dropped_media=0, out_of_scope=0
    )


def test_expression_assets_use_their_own_larger_cap() -> None:
    assert MAX_EXPRESSION_BYTES > MAX_BODY_BYTES
    js = "x" * (MAX_BODY_BYTES + 10)
    html = "<p>" + "y" * (MAX_BODY_BYTES + 10) + "</p>"
    har = har_of(
        make_entry(url="http://127.0.0.1:8000/big.js", content_type="application/javascript", text=js),
        make_entry(url="http://127.0.0.1:8000/big", content_type="text/html", text=html),
    )
    result = parse_har(har, ALLOWED)
    assert [a.url for a in result.expression] == ["http://127.0.0.1:8000/big.js"]
    assert len(result.expression[0].content) == len(js)
    assert [a.url for a in result.documents] == ["http://127.0.0.1:8000/big"]
    assert result.dropped_assets == []


def test_oversized_and_undecodable_assets_are_listed_as_dropped() -> None:
    huge = "x" * (MAX_EXPRESSION_BYTES + 1)
    huge_b64 = base64.b64encode(huge.encode()).decode()
    entries = [
        make_entry(url="http://127.0.0.1:8000/huge.js", content_type="application/javascript", text=huge),
        make_entry(
            url="http://127.0.0.1:8000/huge64.js",
            content_type="application/javascript",
            text=huge_b64,
            encoding="base64",
        ),
        make_entry(
            url="http://127.0.0.1:8000/bad.js",
            content_type="application/javascript",
            text="!!!not base64!!!",
            encoding="base64",
        ),
        make_entry(url="http://127.0.0.1:8000/ok.js", content_type="application/javascript", text="1"),
    ]
    entries[0]["response"]["content"]["size"] = len(huge)
    result = parse_har(har_of(*entries), ALLOWED)
    assert result.dropped_assets == [
        "http://127.0.0.1:8000/huge.js",
        "http://127.0.0.1:8000/huge64.js",
        "http://127.0.0.1:8000/bad.js",
    ]
    assert [a.url for a in result.expression] == ["http://127.0.0.1:8000/ok.js"]


def test_api_bodies_keep_the_small_cap() -> None:
    big = json.dumps({"blob": "x" * (MAX_BODY_BYTES + 10)})
    (ex,) = parse_har(har_of(make_entry(text=big)), ALLOWED).exchanges
    assert ex.error == "body_too_large"
