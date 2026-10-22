import pytest

from reverseai.spec.model import ApiContract, BehaviorSpec, Entity, Evidence, SpecItem
from reverseai.spec.render import render_markdown

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


def make_spec(**over) -> BehaviorSpec:
    base: dict = dict(  # noqa: C408
        product_name="Tasklet",
        summary="Shared task board.",
        features=[
            SpecItem(
                id="F-001",
                title="Create task",
                description="Adds a task.",
                confidence="high",
                evidence=[Evidence(kind="endpoint", ref="POST /api/tasks")],
            )
        ],
        entities=[Entity(name="Task", fields={"id": "integer"}, description="One item.")],
        rules=[
            SpecItem(
                id="R-001",
                title="No duplicates",
                description="Open titles are unique.",
                confidence="medium",
                evidence=[
                    Evidence(kind="endpoint", ref="POST /api/tasks"),
                    Evidence(kind="page", ref="http://t/"),
                ],
            )
        ],
        api=[
            ApiContract(
                method="POST",
                path="/api/tasks",
                request_schema={"type": "object"},
                responses={201: {"type": "object"}, 422: {}},
                description="Create.",
            )
        ],
        gaps=["Rate limits unknown."],
    )
    base.update(over)
    return BehaviorSpec(**base)


def test_render_has_sections_in_order():
    md = render_markdown(make_spec())
    headings = [line for line in md.splitlines() if line.startswith("#")]
    assert headings == [
        "# Tasklet — поведенческая спецификация v1",
        "## Обзор",
        "## Функции",
        "## Сущности",
        "## Правила",
        "## API",
        "## Пробелы",
    ]
    assert "## Правила" in md


def test_render_items_have_confidence_and_evidence():
    md = render_markdown(make_spec())
    assert (
        "- **F-001 Create task** (уверенность: high) — Adds a task. "
        "[evidence: endpoint:POST /api/tasks]"
    ) in md
    assert (
        "- **R-001 No duplicates** (уверенность: medium) — Open titles are unique. "
        "[evidence: endpoint:POST /api/tasks, page:http://t/]"
    ) in md
    assert "- Rate limits unknown." in md
    assert "Shared task board." in md


def test_render_api_and_entities():
    md = render_markdown(make_spec())
    assert "- **POST /api/tasks** — Create." in md
    assert "  - ответ 201:" in md
    assert "  - ответ 422:" in md
    assert "  - запрос:" in md
    assert "`id`: integer" in md


def test_render_empty_sections_and_no_evidence():
    spec = make_spec(features=[], entities=[], rules=[], api=[], gaps=[])
    md = render_markdown(spec)
    for heading in ("## Функции", "## Сущности", "## Правила", "## API", "## Пробелы"):
        assert heading in md
    item = SpecItem(id="F-9", title="T", description="D", confidence="low", evidence=[])
    assert "- **F-9 T** (уверенность: low) — D\n" in render_markdown(make_spec(features=[item]))
