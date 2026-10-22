"""The spec markdown in English (the default language); the Russian copy is in test_render.py."""

from reverseai.i18n import use_language
from reverseai.spec.model import ApiContract, BehaviorSpec, SpecItem
from reverseai.spec.render import render_markdown


def _spec() -> BehaviorSpec:
    return BehaviorSpec(
        product_name="Tasklet",
        summary="Shared task board.",
        features=[SpecItem(id="F-001", title="Create task", description="Adds a task.",
                           confidence="high", evidence=[])],
        api=[ApiContract(method="POST", path="/api/tasks", request_schema={"type": "object"},
                         responses={201: {"type": "object"}})],
        entities=[],
        rules=[],
        gaps=[],
    )


def test_render_in_english_by_default() -> None:
    md = render_markdown(_spec())
    headings = [line for line in md.splitlines() if line.startswith("#")]
    assert headings == [
        "# Tasklet — behavioral spec v1",
        "## Overview",
        "## Features",
        "## Entities",
        "## Rules",
        "## API",
        "## Gaps",
    ]
    assert "- **F-001 Create task** (confidence: high) — Adds a task." in md
    assert '  - request: `{"type":"object"}`' in md
    assert '  - response 201: `{"type":"object"}`' in md


def test_explicit_language_overrides_the_active_one() -> None:
    with use_language("ru"):
        assert render_markdown(_spec(), lang="en").startswith("# Tasklet — behavioral spec v1")
    assert "## Функции" in render_markdown(_spec(), lang="ru")
