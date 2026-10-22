"""Benchmark harness: the whole pipeline on a bundled target, scored by its hidden tests.

The target is served in-process on 127.0.0.1 and marked as a sandbox, so observation submits
forms and probes the API. The release is auto-approved by a bench operator (recorded in the
ledger as `bench.auto_approved`); this shortcut exists only here, never in the CLI pipeline.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from reverseai import pipeline
from reverseai.barrier.release import Approval
from reverseai.bench.server import load_target, serve_asgi
from reverseai.llm.gateway import Gateway
from reverseai.project import Attestation, Mode, Project, ProjectCard, create_project
from reverseai.sandbox.base import Sandbox, free_port
from reverseai.zones.store import Zone

PROJECTS_DIR = "projects"
EVIDENCE_DIR = "evidence"
RESULT_FILE = "bench_result.json"
HIDDEN_JUNIT_FILE = "hidden_tests.xml"

_ACTOR = "bench"
_APPROVER = "bench-operator"
_BRAND_TERMS = ["TaskBoard Pro", "TaskBoard"]
_PRODUCT_NAME = "Tasklet"
_MAX_PAGES = 10
_DELAY_S = 0.05
_HIDDEN_TIMEOUT_S = 300
_OUTPUT_TAIL_CHARS = 2000

GatewayFactory = Callable[[Project], Gateway]
SandboxFactory = Callable[[Path], Sandbox]


class BenchResult(BaseModel):
    target: str
    # scenarios in the released package (what the clean zone built to); parity totals may be
    # smaller: scenarios unstable on the original are excluded from them
    scenarios: int
    parity_ratio: float
    critical_ratio: float
    hidden_passed: int
    hidden_total: int
    cost_usd: float
    duration_s: float
    similarity_max: float


def _card(target: str, base_url: str) -> ProjectCard:
    return ProjectCard(
        name=f"bench-{target}",
        mode=Mode.LEGACY,
        target_base_url=base_url + "/",
        allowed_domains=["127.0.0.1"],
        target_is_sandbox=True,
        attestation=Attestation(
            lawful_access=True,
            basis="internal benchmark",
            signed_by=_APPROVER,
            signed_at=_now(),
        ),
        brand_terms=list(_BRAND_TERMS),
        product_name=_PRODUCT_NAME,
    )


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _auto_approve(project: Project) -> None:
    sha = pipeline.draft_sha256(project)
    project.ledger.append(
        "bench.auto_approved",
        Zone.VERIFIER.value,
        _ACTOR,
        {"auto_approved": True, "approver": _APPROVER, "package_sha256": sha},
    )
    approval = Approval(
        approver=_APPROVER, role="operator", approved_at=_now(), package_sha256=sha
    )
    pipeline.run_release(project, approval)


def _llm_cost(project: Project) -> float:
    return sum(
        float(e.payload.get("cost_usd") or 0.0)
        for e in project.ledger.events()
        if e.type == "llm.call"
    )


def _similarity_max(zip_path: Path) -> float:
    with zipfile.ZipFile(zip_path) as archive:
        return float(json.loads(archive.read("similarity_report.json"))["max_score"])


def _junit_counts(xml_path: Path) -> tuple[int, int]:
    """(passed, total) over every <testsuite> of a pytest junit report."""
    root = ET.parse(xml_path).getroot()
    suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
    total = failed = 0
    for suite in suites:
        tests = int(suite.get("tests", 0))
        total += tests
        failed += sum(int(suite.get(key, 0)) for key in ("failures", "errors", "skipped"))
    return total - failed, total


def run_hidden_tests(tests_dir: Path, base_url: str, junit_xml: Path) -> tuple[int, int]:
    """Run the target's hidden tests against `base_url`; return (passed, total)."""
    junit_xml = Path(junit_xml).resolve()
    junit_xml.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tests_dir), "-q", "-p", "no:cacheprovider",
         "--junitxml", str(junit_xml)],
        env={**os.environ, "BASE_URL": base_url},
        cwd=junit_xml.parent,
        capture_output=True,
        text=True,
        timeout=_HIDDEN_TIMEOUT_S,
        check=False,
    )  # fmt: skip
    tail = (proc.stdout + proc.stderr)[-_OUTPUT_TAIL_CHARS:]
    # pytest exit codes: 0 all passed, 1 some failed; anything else means no usable run.
    if proc.returncode not in (0, 1) or not junit_xml.is_file():
        raise RuntimeError(
            f"hidden tests in {tests_dir} did not run (pytest exit code {proc.returncode}):\n{tail}"
        )
    passed, total = _junit_counts(junit_xml)
    if total == 0:
        raise RuntimeError(f"no tests ran in {tests_dir}:\n{tail}")
    return passed, total


def run_benchmark(
    target: str,
    *,
    gateway: GatewayFactory,
    workdir: Path,
    sandbox_factory: SandboxFactory,
) -> BenchResult:
    """Run every phase on `target` and score the clone; writes `<workdir>/bench_result.json`.

    `gateway` builds the gateway for the bench project (it must log to that project's ledger);
    `sandbox_factory` gets the clone workspace directory and returns a sandbox on it.
    """
    started = time.monotonic()
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    module = load_target(target)
    hidden_tests = Path(module.__file__).parent / "hidden_tests"
    app = module.create_app()
    reset_original = functools.partial(module.reset_state, app)

    with serve_asgi(app) as url:
        project = create_project(_card(target, url), workdir / PROJECTS_DIR)
        pipeline.save_state(project, pipeline.load_state(project))
        llm = gateway(project)
        pipeline.run_observe(
            project, max_pages=_MAX_PAGES, submit_forms=True, probe=True, delay_s=_DELAY_S
        )
        pipeline.run_oracle(project, reset_original=reset_original)
        pipeline.run_spec(project, llm)
        pipeline.run_prepare_release(project)
        _auto_approve(project)
        workspace = pipeline.workspace_dir(project)
        report = pipeline.run_build_loop(
            project,
            llm,
            lambda: sandbox_factory(workspace),
            reset_original=reset_original,
            delay_s=_DELAY_S,
        )
    zip_path = pipeline.run_audit(project, workdir / EVIDENCE_DIR).zip_path

    clone = pipeline.CloneService(sandbox_factory(workspace), free_port())
    try:
        hidden_passed, hidden_total = run_hidden_tests(
            hidden_tests, clone.base_url, workdir / HIDDEN_JUNIT_FILE
        )
    finally:
        clone.stop()

    package = project.store.get_json(pipeline.load_state(project).refs["release"], Zone.VERIFIER)
    result = BenchResult(
        target=target,
        scenarios=len(package["scenarios"]),
        parity_ratio=report.ratio,
        critical_ratio=report.critical_ratio,
        hidden_passed=hidden_passed,
        hidden_total=hidden_total,
        cost_usd=_llm_cost(project),
        duration_s=time.monotonic() - started,
        similarity_max=_similarity_max(zip_path),
    )
    (workdir / RESULT_FILE).write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return result


__all__ = [
    "EVIDENCE_DIR",
    "HIDDEN_JUNIT_FILE",
    "PROJECTS_DIR",
    "RESULT_FILE",
    "BenchResult",
    "GatewayFactory",
    "SandboxFactory",
    "run_benchmark",
    "run_hidden_tests",
]
