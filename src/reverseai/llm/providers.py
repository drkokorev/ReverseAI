"""LLM providers: offline FakeProvider plus Anthropic- and OpenAI-compatible HTTP providers."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from reverseai.config import Settings
from reverseai.llm.types import LLMRequest, LLMResponse, Provider, ProviderError, Usage

RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_ERROR_CHARS = 300


class FakeProvider:
    """Deterministic provider for tests: scripted items first, then an optional responder."""

    def __init__(
        self,
        name: str = "fake",
        script: list[str | Exception] | None = None,
        responder: Callable[[LLMRequest], str] | None = None,
    ):
        self.name = name
        self._script = list(script) if script else []
        self._responder = responder
        self.requests: list[LLMRequest] = []

    def complete(self, req: LLMRequest) -> LLMResponse:
        self.requests.append(req)
        if self._script:
            item = self._script.pop(0)
            if isinstance(item, Exception):
                raise item
            text = item
        elif self._responder is not None:
            text = self._responder(req)
        else:
            raise ProviderError("fake script exhausted", retryable=False)
        chars = len(req.system or "") + sum(len(m.content) for m in req.messages)
        return LLMResponse(
            text=text,
            model=req.model,
            provider=self.name,
            usage=Usage(input_tokens=chars // 4, output_tokens=len(text) // 4),
        )


class _HttpProvider:
    """Shared HTTP plumbing: one POST per request, uniform ProviderError mapping.

    The API key is kept in a private attribute, sent only as a request header, and scrubbed
    from every error message; it never appears in ``repr``.
    """

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        client: httpx.Client | None = None,
        timeout: float = 600,
    ):
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r}, base_url={self._base_url!r})"

    def _scrub(self, text: str) -> str:
        if self._api_key:
            text = text.replace(self._api_key, "***")
        return text[:_MAX_ERROR_CHARS]

    def _post(self, path: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = self._client.post(url, headers=headers, json=body, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise ProviderError(
                self._scrub(f"{self.name}: network error {type(exc).__name__}: {exc}"),
                retryable=True,
            ) from None
        if not response.is_success:
            status = response.status_code
            raise ProviderError(
                self._scrub(f"{self.name}: HTTP {status}: {_error_detail(response)}"),
                retryable=status in RETRYABLE_STATUSES,
                status=status,
            )
        try:
            data = response.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise ProviderError(f"{self.name}: response is not a JSON object", retryable=False)
        return data

    def _malformed(self) -> ProviderError:
        return ProviderError(f"{self.name}: malformed response body", retryable=False)


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str):
            return err
        if payload.get("message"):
            return str(payload["message"])
    return response.text


class AnthropicProvider(_HttpProvider):
    """Anthropic Messages API (also used by Anthropic-compatible gateways)."""

    def complete(self, req: LLMRequest) -> LLMResponse:
        body: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        }
        if req.system:
            body["system"] = req.system
        if req.temperature is not None:
            body["temperature"] = req.temperature
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        data = self._post("/v1/messages", headers, body)
        try:
            text = "".join(
                block.get("text", "") for block in data["content"] if block.get("type") == "text"
            )
            usage = data.get("usage") or {}
            cache_read = int(usage.get("cache_read_input_tokens") or 0)
            cache_write = int(usage.get("cache_creation_input_tokens") or 0)
            # The API's input_tokens excludes cache reads/writes; report the total prompt size.
            parsed = Usage(
                input_tokens=int(usage.get("input_tokens") or 0) + cache_read + cache_write,
                output_tokens=int(usage.get("output_tokens") or 0),
                cached_input_tokens=cache_read,
            )
        except (KeyError, TypeError, AttributeError, ValueError):
            raise self._malformed() from None
        return LLMResponse(text=text, model=req.model, provider=self.name, usage=parsed)


class OpenAICompatProvider(_HttpProvider):
    """OpenAI-style chat completions endpoint (OpenAI and compatible gateways)."""

    def complete(self, req: LLMRequest) -> LLMResponse:
        messages: list[dict[str, str]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.extend({"role": m.role, "content": m.content} for m in req.messages)
        body: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "messages": messages,
        }
        if req.temperature is not None:
            body["temperature"] = req.temperature
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }
        data = self._post("/chat/completions", headers, body)
        try:
            text = data["choices"][0]["message"].get("content") or ""
            usage = data.get("usage") or {}
            details = usage.get("prompt_tokens_details") or {}
            # prompt_tokens already includes the cached tokens.
            parsed = Usage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                cached_input_tokens=int(details.get("cached_tokens") or 0),
            )
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise self._malformed() from None
        return LLMResponse(text=text, model=req.model, provider=self.name, usage=parsed)


def build_providers(
    settings: Settings, env: Mapping[str, str] = os.environ
) -> dict[str, Provider]:
    """Instantiate every configured provider whose API key is present in ``env``.

    ``fake`` providers need no key and are always built.
    """
    providers: dict[str, Provider] = {}
    for key, spec in settings.providers.items():
        if spec.kind == "fake":
            providers[key] = FakeProvider(name=key)
            continue
        api_key = env.get(spec.api_key_env or "", "")
        if not api_key:
            continue
        if not spec.base_url:
            raise ValueError(f"provider {key!r} has no base_url")
        cls = AnthropicProvider if spec.kind == "anthropic" else OpenAICompatProvider
        providers[key] = cls(key, spec.base_url, api_key)
    return providers
