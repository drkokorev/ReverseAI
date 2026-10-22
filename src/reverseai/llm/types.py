"""Provider-neutral LLM request/response types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass
class LLMRequest:
    model: str
    system: str | None
    messages: list[Message]
    max_tokens: int
    temperature: float | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: Usage
    cost_usd: float = 0.0


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class Provider(Protocol):
    name: str

    def complete(self, req: LLMRequest) -> LLMResponse: ...


__all__ = [
    "LLMRequest",
    "LLMResponse",
    "Message",
    "Provider",
    "ProviderError",
    "Usage",
]
