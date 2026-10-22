"""Costs page: the same totals as `reverseai costs`."""

import re

from typer.testing import CliRunner

from reverseai.cli import app as cli_app


def test_costs_match_the_cli(console) -> None:
    c = console("audited")
    out = CliRunner().invoke(cli_app, ["costs", "--project", str(c.project().dir)]).output
    calls = re.search(r"Вызовов LLM: (\d+)", out).group(1)
    total = re.search(r"Стоимость, USD: ([\d.]+)", out).group(1)
    rows = re.findall(r"^  (.+): вызовов (\d+), ([\d.]+) USD$", out, re.MULTILINE)
    assert rows

    html = c.get("/projects/console-demo/costs").text
    assert re.search(rf'data-kpi="calls"[^>]*>{calls}<', html)
    assert f"${total}" in html
    for key, count, cost in rows:
        assert re.search(
            rf"<td[^>]*>{re.escape(key)}</td>\s*<td[^>]*>{count}</td>\s*<td[^>]*>{cost}</td>", html
        ), key
    assert "ПО РОЛЯМ" in html and "ПО МОДЕЛЯМ" in html


def test_costs_without_llm_calls(console) -> None:
    html = console("created").get("/projects/console-demo/costs").text
    assert "Вызовов LLM не было" in html
    assert "$0.0000" in html
