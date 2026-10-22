"""The evidence pack README in English (the default language); Russian: test_evidence.py."""

import re
import zipfile

from reverseai.audit.evidence import build_evidence_pack
from reverseai.audit.similarity import SimilarityReport
from reverseai.parity.differential import ParityReport


def _readme(project, tmp_path, ok: bool = True) -> str:
    parity = ParityReport(
        total=4, passed=3, critical_total=1, critical_passed=1, unstable=["S-009"], results=[],
        skipped_unsafe=["S-010", "S-011"], withheld_mismatches=3,
    )
    similarity = SimilarityReport(0.05, 0.01 if ok else 0.2, {"main.py": 0.01}, ok)
    zip_path = build_evidence_pack(project, parity=parity, similarity=similarity,
                                   brand_hits=["src/a.py:2"], out_dir=tmp_path / "out")
    with zipfile.ZipFile(zip_path) as archive:
        return archive.read("README.md").decode("utf-8")


def test_readme_in_english(project_after_release, tmp_path) -> None:
    readme = _readme(project_after_release, tmp_path)
    for section in (
        "# Evidence pack: Tasklet", "## Ledger integrity", "## Approvals", "## Parity",
        "## Code similarity", "## Brand mentions", "## Implementation sandbox",
        "## Intake risks", "## Models", "This document is not a legal opinion.",
    ):
        assert section in readme, section
    assert "- Status: intact (hash chain verified)" in readme
    assert "package sha256 (spec + scenarios): " in readme
    assert "- Share of scenarios passed: 0.750" in readme
    assert "- Write scenarios skipped (target is not a sandbox): 2" in readme
    assert "- Mismatches on withheld values: 3" in readme
    assert "- Similarity below threshold: yes" in readme
    assert "- m-1 (p): 2 calls, cost $0.7500" in readme
    assert not re.search(r"[А-Яа-яЁё]", readme)


def test_readme_failed_similarity_in_english(project_after_release, tmp_path) -> None:
    readme = _readme(project_after_release, tmp_path, ok=False)
    assert "- Similarity below threshold: no" in readme
