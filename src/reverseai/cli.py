"""Command-line interface (`reverseai`). User-facing messages are in Russian."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
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
from reverseai.messages import (
    ENVIRONMENT_ERRORS,
    PHASE_LABELS,
    USER_ERRORS,
    PlainError,
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

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="ReverseAI: конвейер чистой комнаты для веб-приложений.",
)

# typer's and click's own Exit/Abort subclass RuntimeError; they must pass through untouched.
_CONTROL_FLOW = (typer.Exit, typer.Abort, click.exceptions.Exit, click.exceptions.Abort)

ProjectOpt = Annotated[Path, typer.Option("--project", help="Каталог проекта.")]


@contextlib.contextmanager
def _user_errors() -> Iterator[None]:
    """Report expected failures as one Russian line and exit 1 (no traceback)."""
    try:
        yield
    except _CONTROL_FLOW:
        raise
    except USER_ERRORS as exc:
        typer.echo(f"Ошибка: {user_message(exc)}", err=True)
        raise typer.Exit(1) from None
    except ENVIRONMENT_ERRORS as exc:
        typer.echo(f"Ошибка окружения: {exc}", err=True)
        raise typer.Exit(1) from None


def _project(path: Path) -> Project:
    if not (path / "card.json").is_file():
        raise PlainError(f"проект не найден: {path}")
    return Project.load(path)


@contextlib.contextmanager
def _mutating(path: Path) -> Iterator[Project]:
    """The project, with its lock held for the whole command (D-015); busy → exit 1."""
    project = _project(path)
    with project_lock(project.dir):
        yield project


def _done(phase: Phase) -> None:
    typer.echo(f"Этап «{PHASE_LABELS[phase]}» ({phase.value}) завершён.")


def _plain(value: Any) -> Any:
    """YAML timestamps/dates as ISO strings (card fields are strings)."""
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


@app.command()
def init(
    card: Annotated[Path, typer.Option("--card", help="Карточка проекта (YAML).")],
    projects_root: Annotated[
        Path, typer.Option("--projects-root", help="Каталог, в котором создаётся проект.")
    ],
) -> None:
    """Создать проект из карточки (юридический фильтр)."""
    with _user_errors():
        try:
            data = yaml.safe_load(card.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise PlainError(f"файл карточки не найден: {card}") from None
        project = create_project(ProjectCard.model_validate(_plain(data)), projects_root)
        with project_lock(project.dir):
            pipeline.save_state(project, pipeline.load_state(project))
        typer.echo(f"Проект создан: {project.dir}")
        flags = risk_flags(project.card)
        typer.echo("Флаги риска: " + (", ".join(flags) if flags else "нет"))


@app.command()
def observe(
    project: ProjectOpt,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1)] = 50,
    submit_forms: Annotated[bool, typer.Option("--submit-forms")] = False,
    probe: Annotated[bool, typer.Option("--probe")] = False,
) -> None:
    """Наблюдение: обход цели в браузере и (для песочницы) зондирование API."""
    with _user_errors(), _mutating(project) as p:
        pipeline.run_observe(p, max_pages=max_pages, submit_forms=submit_forms, probe=probe)
        _done(Phase.OBSERVE)


@app.command()
def oracle(project: ProjectOpt) -> None:
    """Построить исполнимые сценарии поведения."""
    with _user_errors(), _mutating(project) as p:
        pipeline.run_oracle(p)
        _done(Phase.ORACLE)


@app.command()
def spec(project: ProjectOpt) -> None:
    """Составить поведенческую спецификацию (аналитик + критик)."""
    with _user_errors(), _mutating(project) as p:
        pipeline.run_spec(p, pipeline.build_gateway(p))
        _done(Phase.SPEC)


@app.command("prepare-release")
def prepare_release(project: ProjectOpt) -> None:
    """Очистить спецификацию и подготовить черновик к согласованию."""
    with _user_errors(), _mutating(project) as p:
        pipeline.run_prepare_release(p)
        sha = pipeline.draft_sha256(p)
        typer.echo(f"Черновик для согласования: {pipeline.release_draft_path(p)}")
        typer.echo(f"SHA-256 пакета (спецификация + сценарии): {sha}")
        typer.echo(
            f"Для выпуска: reverseai approve --project {p.dir} "
            f"--approver <ФИО> --role <operator|customer_analyst> --sha {sha}"
        )


@app.command()
def approve(
    project: ProjectOpt,
    approver: Annotated[str, typer.Option("--approver", help="Кто согласует.")],
    role: Annotated[
        str,
        typer.Option(
            "--role", help="operator (оператор платформы) или customer_analyst (аналитик заказчика)."
        ),
    ],
    sha: Annotated[str, typer.Option("--sha", help="SHA-256 согласуемого пакета (спецификация + сценарии).")],
) -> None:
    """Согласовать черновик и выпустить его в чистую зону."""
    with _user_errors(), _mutating(project) as p:
        approval = Approval(
            approver=approver,
            role=role,
            approved_at=dt.datetime.now(dt.UTC).isoformat(),
            package_sha256=sha,
        )
        pipeline.run_release(p, approval)
        typer.echo(f"Выпуск согласован: {pipeline.load_state(p).refs['release']}")
        _done(Phase.RELEASE)


@app.command()
def build(
    project: ProjectOpt,
    max_rounds: Annotated[int, typer.Option("--max-rounds", min=1)] = 3,
    allow_unstable: Annotated[
        bool,
        typer.Option(
            "--allow-unstable",
            help="Запустить, хотя сценарии изменяют данные песочницы, а сброса между ними нет.",
        ),
    ] = False,
) -> None:
    """Реализация в чистой зоне и проверка паритета (код выхода 2, если порог не достигнут)."""
    with _user_errors(), _mutating(project) as p:
        if p.card.target_is_sandbox and not allow_unstable and pipeline.released_scenarios_write(p):
            raise PlainError(
                "выпущенные сценарии изменяют данные цели, а сбросить её между сценариями "
                "командная строка не умеет: результаты паритета будут нестабильны. "
                "Запустите с --allow-unstable, чтобы продолжить."
            )
        typer.echo("Внимание: LocalSandbox не изолирует код клона от этой машины.")
        workdir = pipeline.workspace_dir(p)
        report = pipeline.run_build_loop(
            p,
            pipeline.build_gateway(p),
            lambda: LocalSandbox(workdir),
            max_rounds=max_rounds,
        )
        met = meets_threshold(report)
        typer.echo(
            f"Паритет: {report.passed}/{report.total} ({report.ratio:.2%}), "
            f"критичные: {report.critical_passed}/{report.critical_total} "
            f"({report.critical_ratio:.2%}), нестабильных: {len(report.unstable)}"
        )
        if report.skipped_unsafe:
            typer.echo(
                "Пропущено сценариев с записью (цель не песочница): "
                f"{len(report.skipped_unsafe)}"
            )
        typer.echo(f"Расхождений по удержанным значениям: {report.withheld_mismatches}")
        typer.echo(f"Рабочий каталог клона: {workdir}")
        typer.echo("Порог достигнут." if met else "Порог не достигнут.")
        if not met:
            raise typer.Exit(2)


@app.command()
def audit(
    project: ProjectOpt,
    out: Annotated[Path, typer.Option("--out", help="Каталог для пакета доказательств.")],
) -> None:
    """Аудит сходства кода и пакет доказательств (код выхода 2, если аудит не пройден)."""
    with _user_errors(), _mutating(project) as p:
        result = pipeline.run_audit(p, out)
        typer.echo(f"Пакет доказательств: {result.zip_path}")
        _done(Phase.AUDIT)
        similarity = result.similarity
        typer.echo(
            f"Максимальное сходство кода: {similarity.max_score:.4f} "
            f"(порог {similarity.threshold})"
        )
        typer.echo(f"Упоминаний бренда в коде: {len(result.brand_hits)}")
        if not result.passed:
            typer.echo("Аудит не пройден.")
            raise typer.Exit(2)


@app.command("ledger-verify")
def ledger_verify(project: ProjectOpt) -> None:
    """Проверить целостность журнала происхождения."""
    with _user_errors():
        result = _project(project).ledger.verify()
        if result.ok:
            typer.echo(f"Журнал цел: цепочка хэшей не нарушена, событий: {result.count}")
            return
        typer.echo(
            f"Целостность журнала нарушена: строка {result.broken_at} ({result.reason})",
            err=True,
        )
        raise typer.Exit(1)


@app.command()
def costs(project: ProjectOpt) -> None:
    """Сводка расходов на LLM по журналу."""
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
        typer.echo(f"Вызовов LLM: {len(calls)}")
        typer.echo(f"Стоимость, USD: {total:.4f}")
        for title, table in (("По ролям:", by_role), ("По моделям:", by_model)):
            if table:
                typer.echo(title)
            for key, (count, cost) in sorted(table.items()):
                typer.echo(f"  {key}: вызовов {int(count)}, {cost:.4f} USD")


@app.command()
def status(project: ProjectOpt) -> None:
    """Показать завершённые этапы и ссылки на артефакты."""
    with _user_errors():
        p = _project(project)
        state = pipeline.load_state(p)
        typer.echo(f"Проект: {p.card.name} ({p.dir})")
        typer.echo("Завершённые этапы:")
        for phase in state.completed:
            typer.echo(f"  - {PHASE_LABELS[phase]} ({phase.value})")
        typer.echo("Артефакты:" if state.refs else "Артефакты: нет")
        for key, ref in sorted(state.refs.items()):
            typer.echo(f"  {key}: {ref}")
        typer.echo(f"Раундов паритета: {state.parity_rounds}")


@app.command()
def bench(
    target: Annotated[str, typer.Option("--target", help="Эталонная цель (bench/targets).")],
    live: Annotated[
        bool, typer.Option("--live", help="Реальные модели из переменных окружения.")
    ] = False,
    workdir: Annotated[
        Path | None, typer.Option("--workdir", help="Каталог прогона.")
    ] = None,
) -> None:
    """Прогнать весь конвейер на эталонной цели и посчитать метрики."""
    if not live:
        typer.echo(
            "Офлайн-прогон бенчмарка (сценарная модель вместо LLM) выполняется только в тестах: "
            "uv run pytest tests/e2e. Для прогона с реальными моделями укажите --live.",
            err=True,
        )
        raise typer.Exit(1)
    with _user_errors():
        if workdir is None:
            stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
            workdir = Path("bench_runs") / f"{target}-{stamp}"
        typer.echo("Внимание: LocalSandbox не изолирует код клона от этой машины.")
        result = bench_runner.run_benchmark(
            target,
            gateway=pipeline.build_gateway,
            workdir=workdir,
            sandbox_factory=LocalSandbox,
        )
        typer.echo(f"Бенчмарк: {result.target}")
        typer.echo(f"Сценариев: {result.scenarios}")
        typer.echo(
            f"Паритет: {result.parity_ratio:.2%}, критичные: {result.critical_ratio:.2%}"
        )
        typer.echo(f"Скрытые тесты: {result.hidden_passed}/{result.hidden_total}")
        typer.echo(f"Максимальное сходство кода: {result.similarity_max:.4f}")
        typer.echo(f"Стоимость, USD: {result.cost_usd:.4f}")
        typer.echo(f"Длительность, с: {result.duration_s:.1f}")
        typer.echo(f"Результат: {workdir / bench_runner.RESULT_FILE}")


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


@app.command()
def console(
    projects_root: Annotated[
        Path, typer.Option("--projects-root", help="Каталог с проектами.")
    ],
    host: Annotated[
        str, typer.Option("--host", help="Адрес сервера (по умолчанию только эта машина).")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8765,
    operator: Annotated[
        str | None,
        typer.Option("--operator", help="Имя оператора: инициалы в шапке, подписант по умолчанию."),
    ] = None,
) -> None:
    """Веб-консоль: проекты, этапы, согласование выпуска, паритет и пакет доказательств."""
    with _user_errors():
        from reverseai.console import create_app
        from reverseai.console.security import LOOPBACK_HOSTS, TOKEN_ENV, is_loopback

        token = os.environ.get(TOKEN_ENV) or None
        loopback = is_loopback(host)
        if not loopback and token is None:
            raise PlainError(
                f"адрес {host} доступен не только с этой машины: задайте токен доступа "
                f"в переменной окружения {TOKEN_ENV} или запустите консоль на 127.0.0.1"
            )
        web = create_app(
            projects_root,
            operator=operator,
            token=token,
            allowed_hosts=[*LOOPBACK_HOSTS, host] if loopback else None,
        )
        shown = f"[{host}]" if ":" in host else host
        url = f"http://{shown}:{port}"
        typer.echo(f"Консоль ReverseAI: {url}")
        if token is not None:
            typer.echo(f"Вход: {url}/login (токен — значение {TOKEN_ENV})")
        typer.echo("Остановить: Ctrl+C")
        _serve(web, host, port)
