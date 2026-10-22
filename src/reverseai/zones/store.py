"""Zone-enforcing, content-addressed artifact store.

This is the single enforcement point of the clean-room barrier: every read goes through
``ArtifactStore.get``, which checks ``READ_RULES`` and refuses (and logs) violations.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from reverseai.provenance.ledger import Ledger

try:  # POSIX; elsewhere only the in-process lock applies
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

_ACTOR = "store"


class Zone(StrEnum):
    DIRTY = "dirty"
    RELEASED = "released"
    CLEAN = "clean"
    VERIFIER = "verifier"


READ_RULES: dict[Zone, set[Zone]] = {
    Zone.DIRTY: {Zone.DIRTY, Zone.RELEASED},
    Zone.RELEASED: {Zone.RELEASED},
    Zone.CLEAN: {Zone.CLEAN, Zone.RELEASED},
    Zone.VERIFIER: set(Zone),
}


@dataclass(frozen=True)
class ArtifactRef:
    id: str  # sha256 hex of the content
    zone: Zone
    kind: str
    name: str
    size: int
    meta: dict = field(default_factory=dict)


class ZoneViolation(Exception):
    """A reader tried to access an artifact its zone is not allowed to read."""


def _ref_to_json(ref: ArtifactRef) -> str:
    obj = {
        "id": ref.id,
        "zone": ref.zone.value,
        "kind": ref.kind,
        "name": ref.name,
        "size": ref.size,
        "meta": ref.meta,
    }
    return json.dumps(obj, ensure_ascii=False)


def _ref_from_json(line: bytes) -> ArtifactRef:
    obj = json.loads(line.decode("utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("meta"), dict):
        raise TypeError("malformed index entry")
    return ArtifactRef(
        id=str(obj["id"]),
        zone=Zone(obj["zone"]),
        kind=str(obj["kind"]),
        name=str(obj["name"]),
        size=int(obj["size"]),
        meta=obj["meta"],
    )


class ArtifactStore:
    def __init__(self, root: Path, ledger: Ledger) -> None:
        self.root = Path(root)
        self.ledger = ledger
        self._lock = threading.Lock()
        self._index_path = self.root / "index.jsonl"
        self._index_lock = self.root / "index.lock"
        self.root.mkdir(parents=True, exist_ok=True)
        for zone in Zone:
            (self.root / zone.value).mkdir(exist_ok=True)
        self._index_size = -1
        self._refs: list[ArtifactRef] = []
        self._refresh()

    def _refresh(self) -> None:
        """Reload the index when another writer (process or store object) appended to it.

        The CLI and the web console share one project: an artifact one of them puts must be
        readable through the other's store. Call with ``self._lock`` held.
        """
        try:
            size = self._index_path.stat().st_size
        except FileNotFoundError:
            size = 0
        if size != self._index_size:
            self._refs = self._load_index()
            self._index_size = size

    @contextlib.contextmanager
    def _exclusive(self):
        """One writer of the index at a time across processes (with ``self._lock`` held)."""
        if fcntl is None:  # pragma: no cover
            yield
            return
        with self._index_lock.open("ab") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _load_index(self) -> list[ArtifactRef]:
        """Parseable index entries in order; unparseable lines (crash residue) are skipped."""
        if not self._index_path.exists():
            return []
        refs: list[ArtifactRef] = []
        for line in self._index_path.read_bytes().split(b"\n"):
            if not line.strip():
                continue
            try:
                refs.append(_ref_from_json(line))
            except (ValueError, TypeError, KeyError):
                continue
        return refs

    def _content_path(self, ref: ArtifactRef) -> Path:
        # Both components are internal: zone is an enum value, id is a sha256 from our index.
        # Caller-supplied ids and names are only ever used for index lookup, never as paths.
        return self.root / ref.zone.value / ref.id

    def _append_index(self, ref: ArtifactRef) -> None:
        line = (_ref_to_json(ref) + "\n").encode("utf-8")
        with self._index_path.open("ab") as f:
            if f.tell() > 0:
                with self._index_path.open("rb") as r:
                    r.seek(-1, os.SEEK_END)
                    if r.read(1) != b"\n":
                        f.write(b"\n")  # isolate crash residue on its own line
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        self._index_size = self._index_path.stat().st_size

    def _find(
        self,
        ref_id: str,
        zone: Zone | None = None,
        kind: str | None = None,
        name: str | None = None,
    ) -> ArtifactRef | None:
        for ref in self._refs:
            if (
                ref.id == ref_id
                and (zone is None or ref.zone == zone)
                and (kind is None or ref.kind == kind)
                and (name is None or ref.name == name)
            ):
                return ref
        return None

    def put(
        self, zone: Zone, kind: str, name: str, data: bytes, meta: dict | None = None
    ) -> ArtifactRef:
        zone = Zone(zone)
        digest = hashlib.sha256(data).hexdigest()
        with self._lock, self._exclusive():
            self._refresh()
            # Content is stored once per zone, but every (kind, name) it is put under keeps its
            # own index entry: `list(kind=...)` (e.g. the barrier's index of the original's
            # expression) must see each one, not only the first put of identical bytes.
            ref = self._find(digest, zone, kind, name)
            if ref is None:
                ref = ArtifactRef(digest, zone, kind, name, len(data), dict(meta or {}))
                path = self._content_path(ref)
                if self._find(digest, zone) is None or not path.exists():
                    tmp = path.with_name(f".{digest}.tmp")
                    tmp.write_bytes(data)
                    os.replace(tmp, path)
                self._append_index(ref)
                self._refs.append(ref)
        self.ledger.append(
            "artifact.put",
            zone.value,
            _ACTOR,
            {"id": ref.id, "kind": ref.kind, "zone": zone.value, "name": ref.name,
             "size": ref.size},
        )
        return ref

    def ref(self, ref_id: str, zone: Zone | None = None, kind: str | None = None) -> ArtifactRef:
        with self._lock:
            self._refresh()
            found = self._find(ref_id, Zone(zone) if zone is not None else None, kind)
        if found is None:
            raise KeyError(ref_id)
        return found

    def get(self, ref_id: str, reader: Zone) -> bytes:
        reader = Zone(reader)
        with self._lock:
            self._refresh()
            candidates = [r for r in self._refs if r.id == ref_id]
        if not candidates:
            raise KeyError(ref_id)
        allowed = READ_RULES[reader]
        ref = next((r for r in candidates if r.zone in allowed), None)
        if ref is None:
            first = candidates[0]
            self.ledger.append(
                "zone.violation",
                reader.value,
                _ACTOR,
                {"id": ref_id, "kind": first.kind, "zone": first.zone.value,
                 "reader": reader.value},
            )
            raise ZoneViolation(
                f"zone {reader.value!r} may not read artifact {ref_id} "
                f"from zone {first.zone.value!r}"
            )
        data = self._content_path(ref).read_bytes()
        if hashlib.sha256(data).hexdigest() != ref.id:
            raise ValueError(f"integrity check failed for artifact {ref.id}")
        self.ledger.append(
            "artifact.read",
            reader.value,
            _ACTOR,
            {"id": ref.id, "kind": ref.kind, "zone": ref.zone.value, "reader": reader.value},
        )
        return data

    def list(self, zone: Zone | None = None, kind: str | None = None) -> list[ArtifactRef]:
        with self._lock:
            self._refresh()
            return [
                r
                for r in self._refs
                if (zone is None or r.zone == Zone(zone)) and (kind is None or r.kind == kind)
            ]

    def put_json(self, zone: Zone, kind: str, name: str, obj: Any) -> ArtifactRef:
        data = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return self.put(zone, kind, name, data)

    def get_json(self, ref_id: str, reader: Zone) -> Any:
        return json.loads(self.get(ref_id, reader).decode("utf-8"))
