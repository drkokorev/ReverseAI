from pathlib import Path

import pytest
from fastapi import FastAPI

from reverseai.bench.runner import run_hidden_tests
from reverseai.bench.server import load_target, serve_asgi

taskboard = load_target("taskboard")
HIDDEN = Path(taskboard.__file__).parent / "hidden_tests"


def test_hidden_tests_are_counted_from_the_junit_report(tmp_path) -> None:
    with serve_asgi(taskboard.create_app()) as url:
        passed, total = run_hidden_tests(HIDDEN, url, tmp_path / "ok.xml")
    assert total > 0
    assert passed == total

    with serve_asgi(FastAPI()) as url:
        broken_passed, broken_total = run_hidden_tests(HIDDEN, url, tmp_path / "broken.xml")
    assert broken_total == total
    assert broken_passed < total


def test_hidden_tests_without_any_test_are_an_error(tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RuntimeError, match="no tests ran"):
        run_hidden_tests(empty, "http://127.0.0.1:1", tmp_path / "r.xml")


def test_hidden_tests_that_cannot_be_collected_are_an_error(tmp_path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "test_x.py").write_text("import not_a_module_anywhere\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not_a_module_anywhere"):
        run_hidden_tests(broken, "http://127.0.0.1:1", tmp_path / "r.xml")
