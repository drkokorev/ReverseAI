from reverseai.oracle.model import Expect, Scenario, ScenarioStep, Step
from reverseai.parity.differential import (
    ParityReport,
    ScenarioParity,
    meets_threshold,
    run_parity,
)


def test_parity_full_on_identical_apps(scenarios, original, faithful_clone) -> None:
    report = run_parity(
        scenarios,
        original.url,
        faithful_clone.url,
        reset_original=original.reset,
        reset_clone=faithful_clone.reset,
    )
    assert report.total == len(scenarios) >= 5
    assert report.passed == report.total
    assert report.unstable == []
    assert report.ratio == 1.0
    assert report.critical_total >= 1
    assert report.critical_ratio == 1.0
    assert all(r.original_ok and r.clone_ok and not r.failures for r in report.results)
    assert meets_threshold(report)


def test_parity_detects_missing_rule(scenarios, original, lenient_clone) -> None:
    report = run_parity(
        scenarios,
        original.url,
        lenient_clone.url,
        reset_original=original.reset,
        reset_clone=lenient_clone.reset,
    )
    failed = [r for r in report.results if not r.clone_ok]
    assert [r.title for r in failed] == [s.title for s in scenarios if "→ 409" in s.title]
    assert failed[0].critical
    assert failed[0].failures[0].kind == "status"
    assert failed[0].failures[0].expected == 409
    assert report.passed == report.total - 1
    assert report.critical_ratio < 1.0
    assert report.ratio < 1.0
    assert not meets_threshold(report)
    assert report.critical_ratio == 0.0
    assert meets_threshold(report, overall=0.8, critical=0.0)


def test_unstable_excluded(original, faithful_clone) -> None:
    good = Scenario(
        id="s001",
        title="GET /api/stats → 200",
        steps=[ScenarioStep(step=Step(method="GET", path="/api/stats"), expect=Expect(status=200))],
    )
    flaky = Scenario(
        id="s002",
        title="GET /api/tasks/{id} → 200",
        critical=True,
        steps=[
            ScenarioStep(step=Step(method="GET", path="/api/tasks/999"), expect=Expect(status=200))
        ],
    )
    report = run_parity(
        [good, flaky],
        original.url,
        faithful_clone.url,
        reset_original=original.reset,
        reset_clone=faithful_clone.reset,
    )
    assert report.unstable == ["s002"]
    assert report.total == 1 and report.passed == 1
    assert report.critical_total == 0 and report.critical_passed == 0
    assert report.critical_ratio == 1.0
    assert [r.id for r in report.results if r.original_ok] == ["s001"]
    unstable = next(r for r in report.results if r.id == "s002")
    assert not unstable.original_ok
    assert not meets_threshold(report)  # the unstable scenario is critical


def test_ratios_are_one_for_empty_denominator() -> None:
    report = ParityReport(
        total=0, passed=0, critical_total=0, critical_passed=0, unstable=[], results=[]
    )
    assert report.ratio == 1.0 and report.critical_ratio == 1.0
    assert not meets_threshold(report)  # nothing compared: the gate must not pass


def test_scenario_parity_model_roundtrip() -> None:
    sp = ScenarioParity(
        id="s1", title="t", critical=False, original_ok=True, clone_ok=True, failures=[]
    )
    assert ScenarioParity.model_validate(sp.model_dump()) == sp


def test_all_unstable_does_not_meet_threshold(original, faithful_clone) -> None:
    flaky = Scenario(
        id="s001",
        title="GET /api/tasks/{id} -> 200",
        critical=True,
        steps=[
            ScenarioStep(step=Step(method="GET", path="/api/tasks/999"), expect=Expect(status=200))
        ],
    )
    report = run_parity(
        [flaky],
        original.url,
        faithful_clone.url,
        reset_original=original.reset,
        reset_clone=faithful_clone.reset,
    )
    assert report.unstable == ["s001"]
    assert report.total == 0
    assert report.ratio == 1.0 and report.critical_ratio == 1.0
    assert not meets_threshold(report)


# --- final review fixes --------------------------------------------------------------------


def _stats_scenario(sid: str, path: str, equals: dict) -> Scenario:
    return Scenario(id=sid, title=f"GET {path}", critical=True, steps=[
        ScenarioStep(step=Step(method="GET", path=path), expect=Expect(status=200,
                                                                      json_equals=equals)),
    ])


def _masked_clone():
    """A clone built from the released package: the path is masked, `/open` is wrong."""
    from fastapi import FastAPI

    from reverseai.bench.server import serve_asgi

    app = FastAPI()

    @app.get("/api/product-stats")
    def stats() -> dict:
        return {"total": 0, "open": 99}

    return serve_asgi(app)


def test_clone_is_checked_against_the_released_projection(original) -> None:
    dirty = [
        _stats_scenario("s1", "/api/stats", {"/total": 0, "/open": 0}),
        _stats_scenario("s2", "/api/stats", {"/total": 0, "/open": 12345}),
    ]
    released = [
        _stats_scenario("s1", "/api/product-stats", {"/total": 0}),  # `/open` withheld
        _stats_scenario("s2", "/api/product-stats", {"/total": 0}),
    ]
    with _masked_clone() as clone_url:
        report = run_parity(dirty, original.url, clone_url, reset_original=original.reset,
                            released=released)
    s1 = next(r for r in report.results if r.id == "s1")
    assert s1.original_ok and s1.clone_ok and s1.failures == []
    assert report.withheld_mismatches == 1  # the clone could not know `/open`
    assert report.unstable == ["s2"]  # the original is still checked with the full scenario
    assert report.total == 1 and report.passed == 1


def test_read_only_original_skips_write_scenarios(scenarios, original, faithful_clone) -> None:
    import httpx

    original.reset()
    report = run_parity(scenarios, original.url, faithful_clone.url,
                        reset_clone=faithful_clone.reset, read_only_original=True)
    writes = [s.id for s in scenarios
              if any(st.step.method not in ("GET", "HEAD") for st in s.steps)]
    assert writes and report.skipped_unsafe == writes
    assert report.total == len(scenarios) - len(writes)
    assert not {r.id for r in report.results} & set(writes)
    stats = httpx.get(original.url + "/api/stats", trust_env=False).json()
    assert stats["total"] == 0  # nothing was written to the original


def _report_with(total: int, unstable: list[tuple[str, bool]]) -> ParityReport:
    results = [ScenarioParity(id=f"ok{i}", title="t", critical=False, original_ok=True,
                              clone_ok=True, failures=[]) for i in range(total)]
    results += [ScenarioParity(id=sid, title="t", critical=critical, original_ok=False,
                               clone_ok=False, failures=[]) for sid, critical in unstable]
    return ParityReport(total=total, passed=total, critical_total=0, critical_passed=0,
                        unstable=[sid for sid, _ in unstable], results=results)


def test_unstable_scenarios_can_fail_the_gate() -> None:
    assert meets_threshold(_report_with(8, [("u1", False), ("u2", False)]))  # 2/10 = 0.2
    assert not meets_threshold(_report_with(7, [("u1", False), ("u2", False)]))  # 2/9 > 0.2
    assert not meets_threshold(_report_with(20, [("u1", True)]))  # a critical one is unstable


def _echo_app(key: str, *, wrong: bool = False, note: str = "a long server sentence"):
    from fastapi import FastAPI, Request

    from reverseai.bench.server import serve_asgi

    app = FastAPI()

    @app.post("/api/x", status_code=201)
    async def create(request: Request) -> dict:
        body = await request.json()
        return {key: "other" if wrong else body.get(key), "note": note}

    return serve_asgi(app)


def _echo_scenario(key: str, equals: dict) -> Scenario:
    return Scenario(id="s1", title="Create", critical=True, steps=[ScenarioStep(
        step=Step(method="POST", path="/api/x", json_body={key: "A"}),
        expect=Expect(status=201, json_equals=equals),
    )])


def test_clone_check_uses_renamed_pointers_of_the_released_projection() -> None:
    dirty = [_echo_scenario("TaskBoard", {"/TaskBoard": "A", "/note": "a long server sentence"})]
    released = [_echo_scenario("Tasklet", {"/Tasklet": "A"})]  # renamed key, `/note` withheld
    with _echo_app("TaskBoard") as original_url:
        with _echo_app("Tasklet", note="clone's own words") as clone_url:
            good = run_parity(dirty, original_url, clone_url, released=released)
        with _echo_app("Tasklet", wrong=True) as clone_url:
            bad = run_parity(dirty, original_url, clone_url, released=released)
    assert good.passed == 1 and good.results[0].failures == []
    assert good.withheld_mismatches == 1  # the clone could not know `/note`
    assert bad.passed == 0
    [failure] = bad.results[0].failures
    assert (failure.kind, failure.pointer, failure.expected) == ("value", "/Tasklet", "A")
