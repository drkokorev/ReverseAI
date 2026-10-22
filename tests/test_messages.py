"""Russian one-line messages shared by the CLI and the console."""

import pytest
from pydantic import ValidationError

from reverseai.messages import user_message, validation_summary
from reverseai.pipeline import PipelineState
from reverseai.project import ProjectCard

# These tests check the Russian copy (English: test_i18n.py and the *_en test modules).
pytestmark = pytest.mark.usefixtures("lang_ru")


def _error(model, raw: str) -> ValidationError:
    with pytest.raises(ValidationError) as info:
        model.model_validate_json(raw)
    return info.value


def test_validation_error_is_one_russian_line_without_urls() -> None:
    exc = _error(ProjectCard, '{"name": 1, "brand_term": ["x"]}')
    text = user_message(exc)
    assert "\n" not in text
    assert "http" not in text and "pydantic" not in text
    assert text.startswith("некорректные данные (ProjectCard): ")
    assert "brand_term — неизвестное поле" in text
    assert "name — ожидается строка" in text
    assert "mode — обязательное поле не задано" in text
    assert f"и ещё {exc.error_count() - 3}" in text


def test_invalid_json_is_named() -> None:
    assert validation_summary(_error(PipelineState, "{bad")) == "некорректный JSON"


def test_unknown_error_types_get_a_generic_label() -> None:
    exc = _error(PipelineState, '{"completed": ["bogus"], "refs": {}}')
    assert validation_summary(exc) == "completed.0 — недопустимое значение"
