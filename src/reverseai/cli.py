"""Command-line interface (`reverseai`). User-facing text comes from the i18n catalogs."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import sys
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import click
import typer
import yaml

from reverseai import pipeline
from reverseai.barrier.release import Approval
from reverseai.bench import runner as bench_runner
from reverseai.i18n import LANG_ENV, LANGS, env_language, normalize, set_language, t
from reverseai.messages import (
    ENVIRONMENT_ERRORS,
    PHASE_LABELS,
    USER_ERRORS,
    PlainError,
    build_summary,
    user_message,
)
from reverseai.parity.differential import meets_threshold
from reverseai.pipeline import Phase
from reverseai.project import (
    Project,
    ProjectCard,
    create_project,
    project_lock,
    risk_flags,
)
from reverseai.sandbox import LocalSandbox


def _help_language(argv: list[str]) -> str:
    """The language of `--help` texts: `--lang` on the command line, else `REVERSEAI_LANG`.

    Help texts are fixed when the commands are defined, before options are parsed, so the
    command line is scanned here; everything printed by a command follows the parsed option.
    """
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return normalize(argv[i + 1]) or env_language()
        if arg.startswith("--lang="):
            return normalize(arg.split("=", 1)[1]) or env_language()
    return env_language()


_HELP_LANG = _help_language(sys.argv[1:])


def _h(key: str) -> str:
    return t(key, lang=_HELP_LANG)


app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help=_h("cli.help.app"),
)

# typer's and click's own Exit/Abort subclass RuntimeError; they must pass through untouched.
_CONTROL_FLOW = (typer.Exit, typer.Abort, click.exceptions.Exit, click.exceptions.Abort)

ProjectOpt = Annotated[Path, typer.Option("--project", help=_h("cli.help.project"))]


@contextlib.contextmanager
def _user_errors() -> Iterator[None]:
    """Report expected failures as one line and exit 1 (no traceback)."""
    try:
        yield
    except _CONTROL_FLOW:
        raise
    except USER_ERRORS as exc:
        typer.echo(t("cli.error", message=user_message(exc)), err=True)
        raise typer.Exit(1) from None
    except ENVIRONMENT_ERRORS as exc:
        typer.echo(t("cli.environment_error", message=exc), err=True)
        raise typer.Exit(1) from None


def _project(path: Path) -> Project:
    if not (path / "card.json").is_file():
        raise PlainError(t("cli.project_not_found", path=path))
    return Project.load(path)


@contextlib.contextmanager
def _mutating(path: Path) -> Iterator[Project]:
    """The project, with its lock held for the whole command (D-015); busy → exit 1."""
    project = _project(path)
    with project_lock(project.dir):
        yield project


def _done(phase: Phase) -> None:
    typer.echo(t("phase_done", label=PHASE_LABELS[phase], phase=phase.value))


def _plain(value: Any) -> Any:
    """YAML timestamps/dates as ISO strings (card fields are strings)."""
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


@app.callback()
def main(
    lang: Annotated[
        str | None,
        typer.Option("--lang", help=_h("cli.help.lang"), show_default=False),
    ] = None,
) -> None:
    code = normalize(lang) if lang is not None else env_language()
    if code is None:
        raise typer.BadParameter(
            t("cli.bad_lang", value=lang, choices=", ".join(LANGS), env=LANG_ENV),
            param_hint="--lang",
        )
    set_language(code)


@app.command(help=_h("cli.help.init"))
def init(
    card: Annotated[Path, typer.Option("--card", help=_h("cli.help.card"))],
    projects_root: Annotated[
        Path, typer.Option("--projects-root", help=_h("cli.help.projects_root_init"))
    ],
) -> None:
    with _user_errors():
        try:
            data = yaml.safe_load(card.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise PlainError(t("cli.card_not_found", path=card)) from None
        project = create_project(ProjectCard.model_validate(_plain(data)), projects_root)
        with project_lock(project.dir):
            pipeline.save_state(project, pipeline.load_state(project))
        typer.echo(t("cli.init.created", path=project.dir))
        flags = risk_flags(project.card)
        typer.echo(t("cli.init.flags", flags=", ".join(flags) if flags else t("common.none")))


@app.command(help=_h("cli.help.observe"))
def observe(
    project: ProjectOpt,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1)] = 50,
    submit_forms: Annotated[bool, typer.Option("--submit-forms")] = False,
    probe: Annotated[bool, typer.Option("--probe")] = False,
) -> None:
    with _user_errors(), _mutating(project) as p:
        pipeline.run_observe(p, max_pages=max_pages, submit_forms=submit_forms, probe=probe)
        _done(Phase.OBSERVE)


@app.command(help=_h("cli.help.oracle"))
def oracle(project: ProjectOpt) -> None:
    with _user_errors(), _mutating(project) as p:
        pipeline.run_oracle(p)
        _done(Phase.ORACLE)


@app.command(help=_h("cli.help.spec"))
def spec(project: ProjectOpt) -> None:
    with _user_errors(), _mutating(project) as p:
        pipeline.run_spec(p, pipeline.build_gateway(p))
        _done(Phase.SPEC)


@app.command("prepare-release", help=_h("cli.help.prepare_release"))
def prepare_release(project: ProjectOpt) -> None:
    with _user_errors(), _mutating(project) as p:
        pipeline.run_prepare_release(p)
        sha = pipeline.draft_sha256(p)
        typer.echo(t("release.draft_for_review", path=pipeline.release_draft_path(p)))
        typer.echo(t("release.package_sha", sha=sha))
        typer.echo(t("cli.prepare_release.next", project=p.dir, sha=sha))


@app.command(help=_h("cli.help.approve"))
def approve(
    project: ProjectOpt,
    approver: Annotated[str, typer.Option("--approver", help=_h("cli.help.approver"))],
    role: Annotated[str, typer.Option("--role", help=_h("cli.help.role"))],
    sha: Annotated[str, typer.Option("--sha", help=_h("cli.help.sha"))],
) -> None:
    with _user_errors(), _mutating(project) as p:
        approval = Approval(
            approver=approver,
            role=role,
            approved_at=dt.datetime.now(dt.UTC).isoformat(),
            package_sha256=sha,
        )
        pipeline.run_release(p, approval)
        typer.echo(t("cli.approve.released", ref=pipeline.load_state(p).refs["release"]))
        _done(Phase.RELEASE)


@app.command(help=_h("cli.help.build"))
def build(
    project: ProjectOpt,
    max_rounds: Annotated[int, typer.Option("--max-rounds", min=1)] = 3,
    allow_unstable: Annotated[
        bool, typer.Option("--allow-unstable", help=_h("cli.help.allow_unstable"))
    ] = False,
) -> None:
    with _user_errors(), _mutating(project) as p:
        if p.card.target_is_sandbox and not allow_unstable and pipeline.released_scenarios_write(p):
            raise PlainError(t("cli.build.unstable_refused"))
        typer.echo(t("build.local_sandbox_warning"))
        workdir = pipeline.workspace_dir(p)
        report = pipeline.run_build_loop(
            p,
            pipeline.build_gateway(p),
            lambda: LocalSandbox(workdir),
            max_rounds=max_rounds,
        )
        met = meets_threshold(report)
        for line in build_summary(report, workdir):
            typer.echo(line)
        typer.echo(t("build.threshold_met") if met else t("build.threshold_missed"))
        if not met:
            raise typer.Exit(2)


@app.command(help=_h("cli.help.audit"))
def audit(
    project: ProjectOpt,
    out: Annotated[Path, typer.Option("--out", help=_h("cli.help.out"))],
) -> None:
    with _user_errors(), _mutating(project) as p:
        result = pipeline.run_audit(p, out)
        typer.echo(t("audit.pack", path=result.zip_path))
        _done(Phase.AUDIT)
        similarity = result.similarity
        typer.echo(
            t("audit.similarity", score=similarity.max_score, threshold=similarity.threshold)
        )
        typer.echo(t("audit.brand_hits", count=len(result.brand_hits)))
        if not result.passed:
            typer.echo(t("audit.failed"))
            raise typer.Exit(2)


@app.command("ledger-verify", help=_h("cli.help.ledger_verify"))
def ledger_verify(project: ProjectOpt) -> None:
    with _user_errors():
        result = _project(project).ledger.verify()
        if result.ok:
            typer.echo(t("cli.ledger.ok", count=result.count))
            return
        typer.echo(t("cli.ledger.broken", line=result.broken_at, reason=result.reason), err=True)
        raise typer.Exit(1)


@app.command(help=_h("cli.help.costs"))
def costs(project: ProjectOpt) -> None:
    with _user_errors():
        calls = [e.payload for e in _project(project).ledger.events() if e.type == "llm.call"]
        by_role: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
        by_model: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
        total = 0.0
        for payload in calls:
            cost = float(payload.get("cost_usd") or 0.0)
            total += cost
            model = f"{payload.get('model')} ({payload.get('provider')})"
            for key, table in ((str(payload.get("role")), by_role), (model, by_model)):
                table[key][0] += 1
                table[key][1] += cost
        typer.echo(t("cli.costs.calls", count=len(calls)))
        typer.echo(t("cli.costs.total", total=total))
        for title, table in ((t("cli.costs.by_role"), by_role),
                             (t("cli.costs.by_model"), by_model)):
            if table:
                typer.echo(title)
            for key, (count, cost) in sorted(table.items()):
                typer.echo(t("cli.costs.row", key=key, count=int(count), cost=cost))


@app.command(help=_h("cli.help.status"))
def status(project: ProjectOpt) -> None:
    with _user_errors():
        p = _project(project)
        state = pipeline.load_state(p)
        typer.echo(t("cli.status.project", name=p.card.name, path=p.dir))
        typer.echo(t("cli.status.completed"))
        for phase in state.completed:
            typer.echo(f"  - {PHASE_LABELS[phase]} ({phase.value})")
        typer.echo(t("cli.status.artifacts") if state.refs else t("cli.status.no_artifacts"))
        for key, ref in sorted(state.refs.items()):
            typer.echo(f"  {key}: {ref}")
        typer.echo(t("cli.status.rounds", count=state.parity_rounds))


@app.command(help=_h("cli.help.bench"))
def bench(
    target: Annotated[str, typer.Option("--target", help=_h("cli.help.target"))],
    live: Annotated[bool, typer.Option("--live", help=_h("cli.help.live"))] = False,
    workdir: Annotated[
        Path | None, typer.Option("--workdir", help=_h("cli.help.workdir"))
    ] = None,
) -> None:
    if not live:
        typer.echo(t("cli.bench.offline"), err=True)
        raise typer.Exit(1)
    with _user_errors():
        if workdir is None:
            stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
            workdir = Path("bench_runs") / f"{target}-{stamp}"
        typer.echo(t("build.local_sandbox_warning"))
        result = bench_runner.run_benchmark(
            target,
            gateway=pipeline.build_gateway,
            workdir=workdir,
            sandbox_factory=LocalSandbox,
        )
        typer.echo(t("cli.bench.target", target=result.target))
        typer.echo(t("cli.bench.scenarios", count=result.scenarios))
        typer.echo(
            t("cli.bench.parity", ratio=result.parity_ratio, critical=result.critical_ratio)
        )
        typer.echo(t("cli.bench.hidden", passed=result.hidden_passed, total=result.hidden_total))
        typer.echo(t("cli.bench.similarity", score=result.similarity_max))
        typer.echo(t("cli.costs.total", total=result.cost_usd))
        typer.echo(t("cli.bench.duration", seconds=result.duration_s))
        typer.echo(t("cli.bench.result", path=workdir / bench_runner.RESULT_FILE))


def _serve(app_: Any, host: str, port: int) -> None:
    import copy

    import uvicorn
    from uvicorn.config import LOGGING_CONFIG

    log_config = copy.deepcopy(LOGGING_CONFIG)  # uvicorn's own, minus query strings
    log_config.setdefault("filters", {})["redact_query"] = {
        "()": "reverseai.console.security.RedactQueryFilter"
    }
    log_config["handlers"]["access"]["filters"] = ["redact_query"]
    uvicorn.run(app_, host=host, port=port, log_level="info", log_config=log_config)


@app.command(help=_h("cli.help.console"))
def console(
    projects_root: Annotated[
        Path, typer.Option("--projects-root", help=_h("cli.help.projects_root"))
    ],
    host: Annotated[str, typer.Option("--host", help=_h("cli.help.host"))] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8765,
    operator: Annotated[
        str | None, typer.Option("--operator", help=_h("cli.help.operator"))
    ] = None,
    lang: Annotated[
        str | None,
        typer.Option("--lang", help=_h("cli.help.console_lang"), show_default=False),
    ] = None,
) -> None:
    with _user_errors():
        from reverseai.console import create_app
        from reverseai.console.security import LOOPBACK_HOSTS, TOKEN_ENV, is_loopback
        from reverseai.i18n import get_language

        default_lang = get_language() if lang is None else normalize(lang)
        if default_lang is None:
            raise typer.BadParameter(
                t("cli.bad_lang", value=lang, choices=", ".join(LANGS), env=LANG_ENV),
                param_hint="--lang",
            )
        set_language(default_lang)  # this command's own output too
        token = os.environ.get(TOKEN_ENV) or None
        loopback = is_loopback(host)
        if not loopback and token is None:
            raise PlainError(t("cli.console.token_required", host=host, env=TOKEN_ENV))
        web = create_app(
            projects_root,
            operator=operator,
            token=token,
            allowed_hosts=[*LOOPBACK_HOSTS, host] if loopback else None,
            lang=default_lang,
        )
        shown = f"[{host}]" if ":" in host else host
        url = f"http://{shown}:{port}"
        typer.echo(t("cli.console.url", url=url))
        if token is not None:
            typer.echo(t("cli.console.login", url=url, env=TOKEN_ENV))
        typer.echo(t("cli.console.stop"))
        _serve(web, host, port)
