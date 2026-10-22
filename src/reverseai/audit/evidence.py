"""Evidence pack: everything an auditor needs to verify the clean-room process."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from reverseai.audit.similarity import SimilarityReport
from reverseai.i18n import t
from reverseai.parity.differential import ParityReport
from reverseai.project import Project, risk_flags, slug
from reverseai.provenance.ledger import LedgerVerification
from reverseai.zones.store import Zone

_ACTOR = "audit"


def _dump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _models_used(events: list) -> list[dict]:
    totals: dict[tuple[str, str], dict] = {}
    for event in events:
        if event.type != "llm.call":
            continue
        key = (str(event.payload.get("model")), str(event.payload.get("provider")))
        row = totals.setdefault(
            key, {"model": key[0], "provider": key[1], "calls": 0, "cost_usd": 0.0}
        )
        row["calls"] += 1
        row["cost_usd"] += float(event.payload.get("cost_usd") or 0.0)
    return sorted(totals.values(), key=lambda r: (r["model"], r["provider"]))


def _zones_access(events: list) -> dict[str, list[dict]]:
    access: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        if event.type != "artifact.read":
            continue
        p = event.payload
        access[str(p.get("reader"))].append(
            {"id": p.get("id"), "kind": p.get("kind"), "zone": p.get("zone")}
        )
    return dict(access)


def _sandbox_line(events: list) -> str:
    """From the latest `implement.start`: was the clone's code run in an isolated sandbox."""
    starts = [e for e in events if e.type == "implement.start"]
    if not starts:
        return "- " + t("evidence.sandbox_never")
    if starts[-1].payload.get("sandbox_isolated"):
        return "- " + t("evidence.sandbox_isolated")
    return "- " + t("evidence.sandbox_not_isolated")


def _readme(
    project: Project,
    verification: LedgerVerification,
    packages: list[dict],
    parity: ParityReport,
    similarity: SimilarityReport,
    brand_hits: list[str],
    models: list[dict],
    events: list,
) -> str:
    """README.md of the pack, in the active language."""
    card = project.card

    def heading(key: str) -> list[str]:
        return ["", "## " + t(f"evidence.{key}"), ""]

    lines = ["# " + t("evidence.title", product=card.product_name)]

    lines += heading("ledger")
    lines.append(
        "- " + (t("evidence.ledger_ok") if verification.ok else t("evidence.ledger_broken"))
    )
    lines.append("- " + t("evidence.ledger_count", count=verification.count))
    if not verification.ok:
        lines.append("- " + t("evidence.ledger_first_broken", line=verification.broken_at,
                              reason=verification.reason))

    lines += heading("approvals")
    approvals = [p.get("approval") or {} for p in packages]
    if approvals:
        for a in approvals:
            lines.append("- " + t(
                "evidence.approval", approver=a.get("approver"), role=a.get("role"),
                approved_at=a.get("approved_at"), sha=a.get("package_sha256"),
            ))
    else:
        lines.append("- " + t("evidence.no_approvals"))

    lines += heading("parity")
    lines += [
        "- " + t("evidence.parity_ratio", ratio=parity.ratio),
        "- " + t("evidence.parity_critical", ratio=parity.critical_ratio),
        "- " + t("evidence.parity_total", count=parity.total),
        "- " + t("evidence.parity_unstable", count=len(parity.unstable)),
        "- " + t("evidence.parity_skipped", count=len(parity.skipped_unsafe)),
        "- " + t("evidence.parity_withheld", count=parity.withheld_mismatches),
    ]
    lines += heading("similarity")
    lines += [
        "- " + t("evidence.similarity_max", score=similarity.max_score,
                 threshold=similarity.threshold),
        "- " + t("evidence.similarity_below",
                 answer=t("common.yes") if similarity.ok else t("common.no")),
    ]
    lines += heading("brand")
    lines += [f"- {hit}" for hit in brand_hits] or ["- " + t("evidence.brand_none")]

    lines += heading("sandbox")
    lines.append(_sandbox_line(events))

    lines += heading("risks")
    lines += [f"- {flag}" for flag in risk_flags(card)] or ["- " + t("evidence.risks_none")]

    lines += heading("models")
    lines += [
        "- " + t("evidence.model_row", model=m["model"], provider=m["provider"],
                 count=m["calls"], cost=m["cost_usd"])
        for m in models
    ] or ["- " + t("evidence.models_none")]

    lines += ["", "---", "", t("evidence.disclaimer"), ""]
    return "\n".join(lines)


def build_evidence_pack(
    project: Project,
    *,
    parity: ParityReport,
    similarity: SimilarityReport,
    brand_hits: list[str],
    out_dir: Path,
) -> Path:
    """Write ``evidence_<slug>/`` and ``evidence_<slug>.zip`` under ``out_dir``; return the zip."""
    name = f"evidence_{slug(project.card.name)}"
    out_dir = Path(out_dir)
    pack_dir = out_dir / name
    zip_path = out_dir / f"{name}.zip"
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    (pack_dir / "release").mkdir(parents=True)

    # Read artifacts first so these verifier reads are part of the ledger snapshot below.
    packages: list[dict] = []
    for ref in project.store.list(Zone.RELEASED, "release_package"):
        package = project.store.get_json(ref.id, Zone.VERIFIER)
        packages.append(package)
        _dump(pack_dir / "release" / f"{ref.id}.json", package)

    verification = project.ledger.verify()
    events = project.ledger.events()
    models = _models_used(events)

    shutil.copyfile(project.ledger.path, pack_dir / "ledger.jsonl")
    _dump(pack_dir / "ledger_verification.json", asdict(verification))
    _dump(pack_dir / "sanitize_report.json", [p.get("sanitize_report") for p in packages])
    (pack_dir / "parity_report.json").write_text(
        parity.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    _dump(pack_dir / "similarity_report.json", asdict(similarity))
    _dump(pack_dir / "models_used.json", models)
    _dump(pack_dir / "zones_access.json", _zones_access(events))
    (pack_dir / "README.md").write_text(
        _readme(
            project, verification, packages, parity, similarity, brand_hits, models, events
        ),
        encoding="utf-8",
    )

    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(pack_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(pack_dir).as_posix())

    project.ledger.append(
        "audit.evidence_pack",
        Zone.VERIFIER.value,
        _ACTOR,
        {"zip": zip_path.name, "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest()},
    )
    return zip_path
