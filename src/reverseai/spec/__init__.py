"""Behavior specification: the only artifact that crosses the clean-room barrier."""

from reverseai.spec.builder import build_spec, critique_spec
from reverseai.spec.model import (
    AnalystDraft,
    ApiContract,
    BehaviorSpec,
    Entity,
    Evidence,
    SpecItem,
)
from reverseai.spec.render import render_markdown

__all__ = [
    "AnalystDraft",
    "ApiContract",
    "BehaviorSpec",
    "Entity",
    "Evidence",
    "SpecItem",
    "build_spec",
    "critique_spec",
    "render_markdown",
]
