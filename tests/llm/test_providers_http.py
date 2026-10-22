import json

import httpx
import pytest

from reverseai.config import load_settings
from reverseai.llm.providers import (
    AnthropicProvider,
    FakeProvider,
    OpenAICompatProvider,
    build_providers,
)
from reverseai.llm.types import LLMRequest, Message, ProviderError, Usage

SECRET = "sk-super-secret-key"


def req(system: str | None = "be brief", temperature: float | None = None) -> LLMRequest:
    return LLMRequest(
        model="m1",
        system=system,
        messages=[Message(role="user", content="hello")],
        max_tokens=64,
        temperature=temperature,
    )


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def anthropic(handler, base_url: str = "https://a.example/") -> AnthropicProvider:
    return AnthropicProvider("anth", base_url, "k", client=client_for(handler))


def openai(handler, base_url: str = "https://o.example/v1") -> OpenAICompatProvider:
    return OpenAICompatProvider("oai", base_url, "k", client=client_for(handler))


def test_anthropic_parses_text_and_usage():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "thinking", "thinking": "..."},
                    {"type": "text", "text": "h"},
                    {"type": "text", "text": "i"},
                ],
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 3,
                    "cache_read_input_tokens": 5,
                    "cache_creation_input_tokens": 2,
                },
            },
        )

    resp = anthropic(handler).complete(req())
    assert resp.text == "hi"
    assert resp.provider == "anth" and resp.model == "m1"
    # input_tokens is the total prompt size: uncached + cache reads + cache writes
    assert resp.usage == Usage(input_tokens=17, output_tokens=3, cached_input_tokens=5)
    assert seen["url"] == "https://a.example/v1/messages"
    assert seen["headers"]["x-api-key"] == "k"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"] == {
        "model": "m1",
        "max_tokens": 64,
        "system": "be brief",
        "messages": [{"role": "user", "content": "hello"}],
    }


def test_anthropic_omits_system_and_sends_temperature_when_set():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1}},
        )

    p = anthropic(handler)
    p.complete(req(system=None))
    p.complete(req(temperature=0.2))
    assert "system" not in bodies[0] and "temperature" not in bodies[0]
    assert bodies[1]["temperature"] == 0.2
    # missing output_tokens / cache fields default to 0
    assert p.complete(req()).usage == Usage(input_tokens=1, output_tokens=0, cached_input_tokens=0)


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 529])
def test_anthropic_retryable_statuses(status):
    p = anthropic(lambda r: httpx.Response(status, json={"error": {"message": "busy"}}))
    with pytest.raises(ProviderError) as ei:
        p.complete(req())
    assert ei.value.retryable is True and ei.value.status == status
    assert "busy" in str(ei.value)


def test_anthropic_429_is_retryable():
    p = anthropic(lambda r: httpx.Response(429, text="slow down"))
    with pytest.raises(ProviderError) as ei:
        p.complete(req())
    assert ei.value.retryable is True
    assert ei.value.status == 429


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_anthropic_client_errors_not_retryable(status):
    p = anthropic(lambda r: httpx.Response(status, text="nope"))
    with pytest.raises(ProviderError) as ei:
        p.complete(req())
    assert ei.value.retryable is False and ei.value.status == status


def test_anthropic_400_not_retryable():
    p = anthropic(lambda r: httpx.Response(400, json={"error": {"message": "bad"}}))
    with pytest.raises(ProviderError) as ei:
        p.complete(req())
    assert ei.value.retryable is False
    assert ei.value.status == 400


def test_network_error_is_retryable():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    for p in (anthropic(boom), openai(boom)):
        with pytest.raises(ProviderError) as ei:
            p.complete(req())
        assert ei.value.retryable is True and ei.value.status is None


def test_timeout_is_retryable():
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(ProviderError) as ei:
        anthropic(slow).complete(req())
    assert ei.value.retryable is True


@pytest.mark.parametrize("payload", ["not json", "[]", '{"content": "x"}'])
def test_anthropic_malformed_success_body_is_non_retryable(payload):
    p = anthropic(lambda r: httpx.Response(200, text=payload))
    with pytest.raises(ProviderError) as ei:
        p.complete(req())
    assert ei.value.retryable is False


def test_openai_parses_and_sends_system_first():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 4,
                    "prompt_tokens_details": {"cached_tokens": 8},
                },
            },
        )

    resp = openai(handler).complete(req(temperature=0.5))
    assert resp.text == "hi"
    assert resp.provider == "oai" and resp.model == "m1"
    # prompt_tokens already includes cached tokens
    assert resp.usage == Usage(input_tokens=12, output_tokens=4, cached_input_tokens=8)
    assert seen["url"] == "https://o.example/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer k"
    body = seen["body"]
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    assert body["messages"][1] == {"role": "user", "content": "hello"}
    assert body["model"] == "m1" and body["temperature"] == 0.5
    assert body["max_tokens"] == 64


def test_openai_without_system_or_cache_details():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": None}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    resp = openai(handler, base_url="https://o.example/v1/").complete(req(system=None))
    assert bodies[0]["messages"][0]["role"] == "user"
    assert "temperature" not in bodies[0]
    assert resp.text == ""
    assert resp.usage == Usage(input_tokens=3, output_tokens=1, cached_input_tokens=0)


def test_openai_errors():
    retry = openai(lambda r: httpx.Response(503, json={"error": {"message": "down"}}))
    with pytest.raises(ProviderError) as ei:
        retry.complete(req())
    assert ei.value.retryable is True and ei.value.status == 503

    bad = openai(lambda r: httpx.Response(401, text="no"))
    with pytest.raises(ProviderError) as ei:
        bad.complete(req())
    assert ei.value.retryable is False and ei.value.status == 401

    empty = openai(lambda r: httpx.Response(200, json={"choices": []}))
    with pytest.raises(ProviderError) as ei:
        empty.complete(req())
    assert ei.value.retryable is False


def test_api_key_never_leaks_into_errors_or_repr():
    def handler(request: httpx.Request) -> httpx.Response:
        # A hostile server echoing the key back must not surface it either.
        return httpx.Response(401, text=f"bad key {request.headers.get('x-api-key')}")

    p = AnthropicProvider("anth", "https://a.example", SECRET, client=client_for(handler))
    with pytest.raises(ProviderError) as ei:
        p.complete(req())
    assert SECRET not in str(ei.value) and SECRET not in repr(ei.value)
    assert SECRET not in repr(p)
    q = OpenAICompatProvider("oai", "https://o.example", SECRET, client=client_for(handler))
    assert SECRET not in repr(q)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach, key={SECRET}")

    r = AnthropicProvider("anth", "https://a.example", SECRET, client=client_for(boom))
    with pytest.raises(ProviderError) as ei2:
        r.complete(req())
    assert SECRET not in str(ei2.value)


def test_build_providers_skips_missing_keys():
    ps = build_providers(load_settings(), env={"ANTHROPIC_API_KEY": "x"})
    assert set(ps) == {"anthropic"}
    assert isinstance(ps["anthropic"], AnthropicProvider)


def test_build_providers_kinds_and_names():
    env = {"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o", "DEEPSEEK_API_KEY": "d", "EMPTY": ""}
    ps = build_providers(load_settings(), env=env)
    assert set(ps) == {"anthropic", "openai", "deepseek"}
    assert isinstance(ps["openai"], OpenAICompatProvider)
    assert isinstance(ps["deepseek"], AnthropicProvider)
    assert [ps[k].name for k in sorted(ps)] == ["anthropic", "deepseek", "openai"]


def test_build_providers_empty_key_is_missing_and_fake_always_built():
    settings = load_settings()
    settings.providers["local"] = settings.providers["anthropic"].model_copy(
        update={"name": "local", "kind": "fake", "api_key_env": None}
    )
    ps = build_providers(settings, env={"ANTHROPIC_API_KEY": ""})
    assert set(ps) == {"local"}
    assert isinstance(ps["local"], FakeProvider) and ps["local"].name == "local"
