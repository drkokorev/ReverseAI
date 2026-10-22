"""Pydantic models for oracle scenarios and their results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Step(BaseModel):
    """One HTTP request; `path` may contain `{var}`, `save` maps var -> JSON pointer."""

    method: str
    path: str
    json_body: Any | None = None
    save: dict[str, str] = {}


class Expect(BaseModel):
    """Expected status, response shape and exact values (keys are JSON pointers)."""

    status: int
    json_shape: dict | None = None
    json_equals: dict[str, Any] = {}


class ScenarioStep(BaseModel):
    step: Step
    expect: Expect


class Scenario(BaseModel):
    id: str
    title: str
    steps: list[ScenarioStep]
    critical: bool = False
    source_exchanges: list[str] = []


class StepFailure(BaseModel):
    step: int
    kind: str  # "status" | "shape" | "value" | "error"
    pointer: str | None
    expected: Any
    actual: Any


class ScenarioResult(BaseModel):
    id: str
    passed: bool
    failures: list[StepFailure]
