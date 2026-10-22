"""The i18n layer: catalogs, language selection, no hardcoded copy, and the English CLI."""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from reverseai import i18n
from reverseai.cli import _help_language, app
from reverseai.i18n import Labels, en, normalize, plural_form, ru, t, use_language
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.pipeline import Phase, load_state, save_state
from reverseai.project import Project
from reverseai.spec.model import AnalystDraft, BehaviorSpec
from reverseai.zones.store import Zone

SRC = Path(__file__).parent.parent / "src" / "reverseai"
FIXTURES = Path(__file__).parent / "fixtures"
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
# The only Cyrillic allowed outside the Russian catalog: the explorer's pattern for a target's
# own destructive buttons ("Удалить", "Выйти"…); it matches the target's UI, it is not copy.
CYRILLIC_ALLOWED = {"observe/explorer.py": ["|удал|очист|сброс|выйти|отмен"]}
PLURAL_FORMS = {"en": {"one", "other"}, "ru": {"one", "few", "many"}}

CARD = {
    "name": "CLI Demo",
    "mode": "legacy",
    "target_base_url": "https://app.example.com/",
    "allowed_domains": ["app.example.com"],
    "attestation": {"lawful_access": True, "basis": "own contract", "signed_by": "Ivan",
                    "signed_at": "2026-10-20T10:00:00Z"},
    "brand_terms": ["TaskBoard Pro"],
    "product_name": "Tasklet",
}
runner = CliRunner()


# --- catalogs ------------------------------------------------------------------------------


def _fields(entry: str | dict) -> set[str]:
    texts = entry.values() if isinstance(entry, dict) else [entry]
    return {name for text in texts for _, name, _, _ in string.Formatter().parse(text) if name}


def test_catalogs_have_the_same_keys_and_placeholders() -> None:
    assert set(en.MESSAGES) == set(ru.MESSAGES)
    for key, entry in en.MESSAGES.items():
        assert _fields(entry) == _fields(ru.MESSAGES[key]), key


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_plural_entries_have_every_form_and_a_count(lang) -> None:
    for key, entry in i18n.CATALOGS[lang].items():
        if isinstance(entry, dict):
            assert set(entry) == PLURAL_FORMS[lang], key
            assert "count" in _fields(entry), key


def test_every_key_used_in_the_code_exists() -> None:
    used: set[str] = set()
    pattern = re.compile(r"""\b(?:t|_h)\(\s*["']([a-z_][a-z0-9_.]*)["']""")
    for path in SRC.rglob("*"):
        if path.suffix in {".py", ".html"} and path.is_file():
            used |= set(pattern.findall(path.read_text(encoding="utf-8")))
    used = {k for k in used if not k.endswith(".")}  # prefixes of computed keys
    assert used, "no keys found"
    missing = sorted(k for k in used if k not in en.MESSAGES)
    assert not missing, missing


def _label_tables() -> list[Labels]:
    from reverseai.console.evidence import FILE_LABELS
    from reverseai.console.forms import JURISDICTIONS, MODE_OPTIONS
    from reverseai.console.jobs import STATUS_LABELS
    from reverseai.console.read.overview import STAGE_NAMES, ZONE_NOTES
    from reverseai.console.read.projects import MODE_LABELS
    from reverseai.console.read.release import FINDING_KINDS, TABS
    from reverseai.console.roles import CONSOLE_ROLES
    from reverseai.messages import PHASE_LABELS

    return [PHASE_LABELS, STAGE_NAMES, ZONE_NOTES, MODE_LABELS, CONSOLE_ROLES, FINDING_KINDS,
            TABS, STATUS_LABELS, JURISDICTIONS, MODE_OPTIONS, FILE_LABELS]


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_label_tables_are_complete(lang) -> None:
    with use_language(lang):
        for table in _label_tables():
            for key in table:
                assert table[key], key


def test_labels_follow_the_active_language() -> None:
    from reverseai.messages import PHASE_LABELS

    assert PHASE_LABELS[Phase.ORACLE] == "Behavior oracle"
    with use_language("ru"):
        assert PHASE_LABELS[Phase.ORACLE] == "Оракул поведения"
    assert Phase.ORACLE in PHASE_LABELS and "nope" not in PHASE_LABELS
    with pytest.raises(KeyError):
        PHASE_LABELS["nope"]


def test_no_cyrillic_outside_the_russian_catalog() -> None:
    offenders = []
    for path in sorted(SRC.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".html", ".js", ".css", ".yaml"}:
            continue
        rel = path.relative_to(SRC).as_posix()
        if rel == "i18n/ru.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not CYRILLIC.search(line):
                continue
            if any(allowed in line for allowed in CYRILLIC_ALLOWED.get(rel, [])):
                continue
            offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


# --- lookup --------------------------------------------------------------------------------


@pytest.mark.parametrize(("n", "form"), [(0, "many"), (1, "one"), (2, "few"), (4, "few"),
                                         (5, "many"), (11, "many"), (12, "many"), (21, "one"),
                                         (22, "few"), (111, "many"), (101, "one")])
def test_russian_plural_forms(n, form) -> None:
    assert plural_form("ru", n) == form


def test_english_plural_forms() -> None:
    assert [plural_form("en", n) for n in (0, 1, 2, 21)] == ["other", "one", "other", "other"]
    assert t("kpi.calls", count=1) == "1 call"
    assert t("kpi.calls", count=3) == "3 calls"
    assert t("kpi.calls", lang="ru", count=3) == "3 вызова"
    assert t("kpi.calls", lang="ru", count=5) == "5 вызовов"


def test_default_language_is_english_and_env_selects_another(monkeypatch) -> None:
    assert i18n.get_language() == "en"
    assert i18n.env_language() == "en"
    monkeypatch.setenv("REVERSEAI_LANG", "ru_RU")
    assert i18n.env_language() == "ru"
    monkeypatch.setenv("REVERSEAI_LANG", "de")
    assert i18n.env_language() == "en"


def test_normalize_and_set_language() -> None:
    assert [normalize(x) for x in ("en", "RU", "ru-RU", "de", "", None)] == [
        "en", "ru", "ru", None, None, None]
    with pytest.raises(ValueError, match="unsupported language"):
        i18n.set_language("de")


def test_unknown_key_is_an_error() -> None:
    with pytest.raises(KeyError):
        t("no.such.key")


# --- CLI -----------------------------------------------------------------------------------


def invoke(*args):
    return runner.invoke(app, [str(a) for a in args])


def _init(tmp_path: Path, **over) -> tuple:
    card = tmp_path / "card.yaml"
    card.write_text(yaml.safe_dump({**CARD, **over}, allow_unicode=True), encoding="utf-8")
    result = invoke("init", "--card", card, "--projects-root", tmp_path / "projects")
    return result, tmp_path / "projects" / "cli-demo"


def test_cli_status_and_ledger_verify_in_english(tmp_path) -> None:
    result, project_dir = _init(tmp_path)
    assert result.exit_code == 0, result.output
    assert f"Project created: {project_dir}" in result.output
    assert "Risk flags: read_only_observation" in result.output
    result = invoke("status", "--project", project_dir)
    assert "Project: CLI Demo" in result.output
    assert "Completed phases:\n  - Project intake (intake)" in result.output
    assert "Parity rounds: 0" in result.output
    result = invoke("ledger-verify", "--project", project_dir)
    assert result.exit_code == 0
    assert "Ledger intact: hash chain unbroken, events:" in result.output
    assert not CYRILLIC.search(result.output)


def test_cli_ledger_tampering_in_english(tmp_path) -> None:
    _, project_dir = _init(tmp_path)
    ledger = project_dir / "ledger.jsonl"
    ledger.write_text(ledger.read_text(encoding="utf-8").replace("CLI Demo", "CLI Dem0"),
                      encoding="utf-8")
    result = invoke("ledger-verify", "--project", project_dir)
    assert result.exit_code == 1
    assert "Ledger integrity broken: line" in result.output


def test_cli_costs_in_english(tmp_path) -> None:
    _, project_dir = _init(tmp_path)
    project = Project.load(project_dir)
    for role, model, cost in [("analyst", "m-1", 0.5), ("analyst", "m-1", 0.25),
                              ("executor", "m-2", 1.0)]:
        project.ledger.append("llm.call", "dirty", role, {
            "role": role, "model": model, "provider": "p", "usage": {}, "cost_usd": cost,
        })
    lines = invoke("costs", "--project", project_dir).output.splitlines()
    assert "LLM calls: 3" in lines
    assert "Cost, USD: 1.7500" in lines
    assert "By role:" in lines and "By model:" in lines
    assert "  analyst: 2 calls, 0.7500 USD" in lines
    assert "  m-2 (p): 1 call, 1.0000 USD" in lines


def test_cli_errors_in_english(tmp_path) -> None:
    result = invoke("status", "--project", tmp_path / "nope")
    assert result.exit_code == 1
    assert f"Error: project not found: {tmp_path / 'nope'}" in result.output

    attestation = {**CARD["attestation"], "lawful_access": False}
    result, _ = _init(tmp_path, attestation=attestation)
    assert result.exit_code == 1
    assert ("Error: project intake check failed: attestation of lawful access is required"
            in result.output)

    result, _ = _init(tmp_path, product_name="TaskBoard Pro Clone")
    assert ("Error: project intake check failed: product name 'TaskBoard Pro Clone' reuses a "
            "brand term") in result.output

    result, project_dir = _init(tmp_path)
    result = invoke("oracle", "--project", project_dir)
    assert result.exit_code == 1
    assert "Error: complete the “Observation” phase first (observe)" in result.output

    path = tmp_path / "bad.yaml"
    path.write_text("name: x\n", encoding="utf-8")
    result = invoke("init", "--card", path, "--projects-root", tmp_path / "p2")
    assert ("Error: invalid data (ProjectCard): mode — required field is missing; "
            "target_base_url — required field is missing;") in result.output
    assert re.search(r"; and \d+ more$", result.output.rstrip())


def _spec_ready(project_dir: Path) -> None:
    project = Project.load(project_dir)
    draft = AnalystDraft.model_validate_json(
        (FIXTURES / "llm" / "analyst_spec.json").read_text(encoding="utf-8")
    )
    spec = BehaviorSpec(product_name="Tasklet", api=[], **draft.model_dump())
    scenario = Scenario(id="s001", title="Create a task", steps=[
        ScenarioStep(step=Step(method="POST", path="/api/tasks", json_body={"title": "Milk"}),
                     expect=Expect(status=201)),
    ])
    state = load_state(project)
    state.refs["spec"] = project.store.put_json(
        Zone.DIRTY, "spec", "spec", spec.model_dump(mode="json")).id
    state.refs["scenarios"] = project.store.put_json(
        Zone.DIRTY, "scenarios", "scenarios", [scenario.model_dump(mode="json")]).id
    state.completed += [Phase.OBSERVE, Phase.ORACLE, Phase.SPEC]
    save_state(project, state)


def test_cli_prepare_release_and_approve_errors_in_english(tmp_path) -> None:
    _, project_dir = _init(tmp_path)
    result = invoke("approve", "--project", project_dir, "--approver", "Petrov",
                    "--role", "operator", "--sha", "0" * 64)
    assert "Error: complete the “Release preparation” phase first (prepare_release)" in (
        result.output)

    _spec_ready(project_dir)
    result = invoke("prepare-release", "--project", project_dir)
    assert result.exit_code == 0, result.output
    assert f"Draft for approval: {project_dir / 'release_draft.md'}" in result.output
    assert "Package SHA-256 (spec + scenarios): " in result.output
    assert "--approver <NAME> --role <operator|customer_analyst>" in result.output
    markdown = (project_dir / "release_draft.md").read_text(encoding="utf-8")
    assert markdown.startswith("# Tasklet — behavioral spec v1")

    result = invoke("approve", "--project", project_dir, "--approver", "Petrov",
                    "--role", "operator", "--sha", "0" * 64)
    assert result.exit_code == 1
    assert ("Error: release through the barrier refused: approval does not match the draft "
            "package hash") in result.output
    result = invoke("approve", "--project", project_dir, "--approver", "Petrov",
                    "--role", "boss", "--sha", "0" * 64)
    assert result.exit_code == 1
    assert "Error: invalid data (Approval): role — invalid value" in result.output


def test_lang_option_and_env_switch_the_cli_to_russian(tmp_path, monkeypatch) -> None:
    _, project_dir = _init(tmp_path)
    result = invoke("--lang", "ru", "status", "--project", project_dir)
    assert "Завершённые этапы:" in result.output and "Приём проекта" in result.output
    result = invoke("status", "--project", project_dir)
    assert "Completed phases:" in result.output  # the option lasts for one command

    monkeypatch.setenv("REVERSEAI_LANG", "ru")
    assert "Завершённые этапы:" in invoke("status", "--project", project_dir).output
    assert "Completed phases:" in invoke("--lang", "en", "status", "--project",
                                         project_dir).output


def test_unsupported_lang_is_refused(tmp_path) -> None:
    result = invoke("--lang", "de", "status", "--project", tmp_path)
    assert result.exit_code == 2
    assert "unsupported language “de”" in result.output


def test_help_language_follows_the_command_line_then_the_env(monkeypatch) -> None:
    assert _help_language([]) == "en"
    assert _help_language(["--lang", "ru", "init", "--help"]) == "ru"
    assert _help_language(["--lang=ru"]) == "ru"
    monkeypatch.setenv("REVERSEAI_LANG", "ru")
    assert _help_language(["--help"]) == "ru"
    assert _help_language(["--lang", "en"]) == "en"


def test_cli_help_is_english_by_default() -> None:
    result = invoke("--help")
    assert "a clean-room pipeline for web applications" in result.output
    assert "Interface language" in result.output
