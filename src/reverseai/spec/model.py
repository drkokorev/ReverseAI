"""Behavior spec data model."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel


class Evidence(BaseModel):
    kind: Literal["page", "exchange", "endpoint", "doc", "expert"]
    ref: str


class SpecItem(BaseModel):
    id: str
    title: str
    description: str
    confidence: Literal["high", "medium", "low"]
    evidence: list[Evidence]


class Entity(BaseModel):
    name: str
    fields: dict[str, str]
    description: str


class ApiContract(BaseModel):
    method: str
    path: str
    request_schema: dict | None
    responses: dict[int, dict]
    description: str = ""


class AnalystDraft(BaseModel):
    """The LLM-produced part of the spec."""

    summary: str
    features: list[SpecItem]
    entities: list[Entity]
    rules: list[SpecItem]
    gaps: list[str]


class BehaviorSpec(BaseModel):
    version: int = 1
    product_name: str
    summary: str
    features: list[SpecItem]
    entities: list[Entity]
    rules: list[SpecItem]
    api: list[ApiContract]
    gaps: list[str]

    def sha256(self) -> str:
        """SHA-256 hex of the canonical JSON form of the spec."""
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
