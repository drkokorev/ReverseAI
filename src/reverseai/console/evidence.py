"""Where the console's audit writes the evidence pack, and what is in it.

The console runs the audit with `<project>/evidence` as the output directory (the CLI takes it
from `--out`); the pack's own files are read from there for display, but only while that zip is
the pack of the latest audit (its SHA-256 matches the last `audit.evidence_pack` event). After
an audit with another `--out` the pack there is stale: the console says the pack was built
outside it instead of showing the old one.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from reverseai.i18n import Labels, t
from reverseai.project import Project, slug
from reverseai.provenance.ledger import LedgerEvent

EVIDENCE_DIR = "evidence"

# What each file of the pack holds (shown next to the file list).
FILE_LABELS: Labels[str] = Labels(
    "evidence_file",
    [
        "README.md", "ledger.jsonl", "ledger_verification.json", "release",
        "sanitize_report.json", "parity_report.json", "similarity_report.json",
        "models_used.json", "zones_access.json",
    ],
    name=lambda entry: entry.split(".")[0],
)


def evidence_dir(project: Project) -> Path:
    return project.dir / EVIDENCE_DIR


def _name(project: Project) -> str:
    return f"evidence_{slug(project.card.name)}"


def evidence_zip(project: Project) -> Path:
    return evidence_dir(project) / f"{_name(project)}.zip"


def outside_console() -> str:
    """Why the pack cannot be downloaded: the latest audit wrote it elsewhere (one sentence)."""
    return t("evidence_outside")


def current_pack(project: Project, events: list[LedgerEvent]) -> Path | None:
    """The console's evidence zip if it is the pack of the latest audit, else None."""
    path = evidence_zip(project)
    latest = next((e for e in reversed(events) if e.type == "audit.evidence_pack"), None)
    if latest is None or not path.is_file():
        return None
    if latest.payload.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
        return None
    return path


def evidence_files(project: Project) -> list[tuple[str, str]]:
    """(entry, label) of the zip's top level: files, and directories as `name/`."""
    path = evidence_zip(project)
    if not path.is_file():
        return []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    entries: list[str] = []
    for name in names:
        top = name.split("/", 1)[0] + ("/" if "/" in name else "")
        if top not in entries:
            entries.append(top)
    return [(entry, FILE_LABELS.get(entry.rstrip("/"), "")) for entry in entries]


def similarity_report(project: Project) -> dict | None:
    """`similarity_report.json` of the pack (None before the audit)."""
    path = evidence_dir(project) / _name(project) / "similarity_report.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
