import hashlib
from pathlib import Path

from reverseai.barrier.sanitizer import build_expression_index, tokenize
from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step, StepFailure
from reverseai.parity.differential import ParityReport, ScenarioParity, run_parity
from reverseai.parity.feedback import MAX_FEEDBACK_LINES, feedback_for_clean_zone
from reverseai.provenance.ledger import Ledger

APP_JS = (
    Path(__file__).resolve().parents[2] / "bench/targets/taskboard/static/app.js"
).read_text(encoding="utf-8")
JS_SLICE = "That title is too long (200 characters max)"
KW = {"brand_terms": ["TaskBoard Pro"], "product_name": "the product", "target_domains": []}


def _index():
    return build_expression_index([APP_JS])


def _scenario(id: str, title: str, *, method="POST", path="/api/tasks/{v0}", n_steps=2) -> Scenario:
    steps = [
        ScenarioStep(step=Step(method="GET", path="/api/stats"), expect=Expect(status=200))
        for _ in range(n_steps - 1)
    ]
    steps.append(ScenarioStep(step=Step(method=method, path=path), expect=Expect(status=200)))
    return Scenario(id=id, title=title, steps=steps, critical=True)


def _report(*pairs: tuple[Scenario, StepFailure | None]) -> ParityReport:
    results = [
        ScenarioParity(
            id=s.id,
            title=s.title,
            critical=s.critical,
            original_ok=True,
            clone_ok=f is None,
            failures=[f] if f else [],
        )
        for s, f in pairs
    ]
    ok = sum(r.clone_ok for r in results)
    return ParityReport(
        total=len(results),
        passed=ok,
        critical_total=len(results),
        critical_passed=ok,
        unstable=[],
        results=results,
    )


def test_feedback_from_real_parity_run(scenarios, original, lenient_clone) -> None:
    report = run_parity(
        scenarios,
        original.url,
        lenient_clone.url,
        reset_original=original.reset,
        reset_clone=lenient_clone.reset,
    )
    lines = feedback_for_clean_zone(report, scenarios, _index(), **KW)
    [duplicate] = [s for s in scenarios if "→ 409" in s.title]
    assert lines == [f"{duplicate.title}: step 2 POST /api/tasks: expected status = 409"]


def test_feedback_withholds_long_and_verbatim() -> None:
    long_value = "x" * 200
    s_long = _scenario("s1", "long value")
    s_js = _scenario("s2", "verbatim value")
    s_ok = _scenario("s3", "short value")
    report = _report(
        (s_long, StepFailure(step=1, kind="value", pointer="/error", expected=long_value, actual="")),
        (s_js, StepFailure(step=1, kind="value", pointer="/error", expected=JS_SLICE, actual="")),
        (s_ok, StepFailure(step=1, kind="value", pointer="/error", expected="duplicate", actual="")),
    )
    lines = feedback_for_clean_zone(report, [s_long, s_js, s_ok], _index(), **KW)
    assert lines == [
        "long value: step 2 POST /api/tasks/{v0}: expected value /error = (value withheld)",
        "verbatim value: step 2 POST /api/tasks/{v0}: expected value /error = (value withheld)",
        "short value: step 2 POST /api/tasks/{v0}: expected value /error = duplicate",
    ]
    index = _index()
    for line in lines:
        assert index.contains_span(tokenize(line)) == []


def test_feedback_never_leaks_actual_or_non_scalars() -> None:
    s1 = _scenario("s1", "nested")
    s2 = _scenario("s2", "numbers")
    report = _report(
        (s1, StepFailure(step=0, kind="value", pointer="/a", expected={"k": "v"}, actual="SECRET-ACTUAL")),
        (s2, StepFailure(step=1, kind="shape", pointer="/id", expected="integer", actual="SECRET-ACTUAL")),
    )
    lines = feedback_for_clean_zone(report, [s1, s2], _index(), **KW)
    assert lines == [
        "nested: step 1 GET /api/stats: expected value /a = (value withheld)",
        "numbers: step 2 POST /api/tasks/{v0}: expected shape /id = integer",
    ]
    assert not any("SECRET-ACTUAL" in line for line in lines)


def test_feedback_error_kind_without_pointer_and_title_sanitized() -> None:
    title = f"TaskBoard Pro flow: {JS_SLICE} and more words here"
    s = _scenario("s1", title)
    report = _report((s, StepFailure(step=1, kind="error", pointer=None, expected="v0", actual=None)))
    [line] = feedback_for_clean_zone(report, [s], _index(), **KW)
    assert "TaskBoard Pro" not in line
    assert JS_SLICE not in line
    assert line.endswith("step 2 POST /api/tasks/{v0}: expected error = v0")
    assert _index().contains_span(tokenize(line)) == []


def test_feedback_skips_passing_and_unstable_and_caps_lines() -> None:
    many = [_scenario(f"s{i}", f"scenario {i}") for i in range(40)]
    failing = [
        (s, StepFailure(step=1, kind="status", pointer=None, expected=409, actual=200))
        for s in many
    ]
    passing = _scenario("ok", "passing")
    report = _report(*failing, (passing, None))
    report.results.append(
        ScenarioParity(
            id="u", title="unstable", critical=False, original_ok=False, clone_ok=False, failures=[]
        )
    )
    lines = feedback_for_clean_zone(report, [*many, passing], _index(), **KW)
    assert len(lines) == MAX_FEEDBACK_LINES == 30
    assert lines[0] == "scenario 0: step 2 POST /api/tasks/{v0}: expected status = 409"
    assert not any("passing" in line or "unstable" in line for line in lines)


def test_feedback_records_ledger_event(tmp_path: Path) -> None:
    s = _scenario("s1", "one")
    report = _report((s, StepFailure(step=1, kind="status", pointer=None, expected=409, actual=200)))
    ledger = Ledger(tmp_path / "ledger.jsonl")
    lines = feedback_for_clean_zone(report, [s], _index(), ledger=ledger, **KW)
    [event] = [e for e in ledger.events() if e.type == "parity.feedback"]
    assert event.zone == "verifier" and event.actor == "parity"
    assert event.payload == {
        "lines": 1,
        "sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest(),
    }
    assert ledger.verify().ok


def test_feedback_lists_critical_failures_first_under_the_cap() -> None:
    plain = [_scenario(f"p{i}", f"plain {i}") for i in range(35)]
    for s in plain:
        s.critical = False
    crit = _scenario("c1", "critical one")
    fail = StepFailure(step=1, kind="status", pointer=None, expected=409, actual=200)
    report = _report(*[(s, fail) for s in plain], (crit, fail))
    lines = feedback_for_clean_zone(report, [*plain, crit], _index(), **KW)
    assert len(lines) == 30
    assert lines[0].startswith("critical one:")


def test_feedback_status_with_non_int_expected_uses_value_rule() -> None:
    s = _scenario("s1", "odd status")
    report = _report(
        (s, StepFailure(step=1, kind="status", pointer=None, expected="y" * 200, actual=200))
    )
    [line] = feedback_for_clean_zone(report, [s], _index(), **KW)
    assert line.endswith("expected status = (value withheld)")


def test_feedback_withholds_short_server_prose() -> None:
    s = _scenario("s1", "duplicate")
    prose = "A task with this title already exists"
    report = _report((s, StepFailure(step=1, kind="value", pointer="/message", expected=prose,
                                     actual="")))
    [line] = feedback_for_clean_zone(report, [s], _index(), **KW)
    assert prose not in line
    assert line.endswith("expected value /message = (value withheld)")


def test_feedback_shows_values_the_scenario_itself_sent() -> None:
    s = _scenario("s1", "echo")
    s.steps[-1].step.json_body = {"title": "write report"}
    report = _report((s, StepFailure(step=1, kind="value", pointer="/title",
                                     expected="write report", actual="")))
    [line] = feedback_for_clean_zone(report, [s], _index(), **KW)
    assert line.endswith("expected value /title = write report")


def test_feedback_shows_released_paths_and_pointers_by_the_identifier_rule() -> None:
    path = "/api/v1/tasks?status=open&page=2&per_page=20"
    pointer = "/items/0/owner/display_name/first/part/of/it"
    index = build_expression_index([
        APP_JS, f"fetch('{path}')", "items/0/owner/display_name/first/part/of/it",
    ])
    s = _scenario("s1", "list", method="GET", path=path)
    report = _report((s, StepFailure(step=1, kind="value", pointer=pointer, expected=1,
                                     actual=2)))
    [line] = feedback_for_clean_zone(report, [s], index, **KW)
    assert line == f"list: step 2 GET {path}: expected value {pointer} = 1"


def test_feedback_masks_brand_in_a_path_or_pointer() -> None:
    s = _scenario("s1", "list", method="GET", path="/api/taskboard-pro/items")
    report = _report((s, StepFailure(step=1, kind="value", pointer="/taskboard_pro_id",
                                     expected=1, actual=2)))
    [line] = feedback_for_clean_zone(report, [s], _index(), **KW)
    assert "taskboard" not in line.lower()
    assert line == "list: step 2 GET /api/the-product/items: expected value /theproduct_id = 1"


def test_feedback_uses_the_released_title() -> None:
    s = _scenario("s1", "Create a task")
    report = _report((s, StepFailure(step=1, kind="status", pointer=None, expected=409,
                                     actual=200)))
    report.results[0].title = "POST /api/tasks → 409 on the original"
    [line] = feedback_for_clean_zone(report, [s], _index(), **KW)
    assert line.startswith("Create a task: ")
