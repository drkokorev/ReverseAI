"""`reverseai console`: loopback by default, a token for any other address."""

from typer.testing import CliRunner

from reverseai import cli

runner = CliRunner()


def _capture(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(cli, "_serve", lambda app, host, port: calls.append(
        {"app": app, "host": host, "port": port}))
    return calls


def test_console_binds_loopback_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("REVERSEAI_CONSOLE_TOKEN", raising=False)
    calls = _capture(monkeypatch)
    result = runner.invoke(cli.app, ["console", "--projects-root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    [call] = calls
    assert (call["host"], call["port"]) == ("127.0.0.1", 8765)
    ctx = call["app"].state.console
    assert ctx.projects.root == tmp_path
    assert ctx.token is None
    assert "http://127.0.0.1:8765" in result.output


def test_console_refuses_a_public_address_without_a_token(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("REVERSEAI_CONSOLE_TOKEN", raising=False)
    calls = _capture(monkeypatch)
    result = runner.invoke(
        cli.app, ["console", "--projects-root", str(tmp_path), "--host", "0.0.0.0"]
    )
    assert result.exit_code == 1
    assert "REVERSEAI_CONSOLE_TOKEN" in result.output
    assert "Ошибка:" in result.output
    assert calls == []


def test_console_on_a_public_address_with_a_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REVERSEAI_CONSOLE_TOKEN", "t0ken-value")
    calls = _capture(monkeypatch)
    result = runner.invoke(
        cli.app,
        ["console", "--projects-root", str(tmp_path), "--host", "0.0.0.0", "--port", "9000",
         "--operator", "Даниил Кокорев"],
    )
    assert result.exit_code == 0, result.output
    [call] = calls
    ctx = call["app"].state.console
    assert ctx.token == "t0ken-value"
    assert ctx.operator == "Даниил Кокорев"
    assert "t0ken-value" not in result.output
    assert "http://0.0.0.0:9000/login" in result.output
    assert "?token=" not in result.output


def test_serve_redacts_query_strings_in_the_access_log(monkeypatch) -> None:
    import uvicorn

    calls: list[dict] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    cli._serve(object(), "127.0.0.1", 8765)
    [kwargs] = calls
    config = kwargs["log_config"]
    assert "redact_query" in config["handlers"]["access"]["filters"]
    assert config["filters"]["redact_query"]["()"].endswith("RedactQueryFilter")
