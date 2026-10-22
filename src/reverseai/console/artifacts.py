"""Artifact reads for display, cached per process.

Artifact ids are content hashes, so a decoded artifact never changes: the console reads each
one once per server run through `ArtifactStore.get(..., Zone.VERIFIER)` (which logs the read)
and serves later page views from memory.
"""

from __future__ import annotations

import threading
from typing import Any

from reverseai.project import Project
from reverseai.zones.store import Zone


class ArtifactCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._json: dict[tuple[str, str], Any] = {}
        self._bytes: dict[tuple[str, str], bytes] = {}

    def json(self, project: Project, ref_id: str) -> Any:
        key = (str(project.dir.resolve()), ref_id)
        with self._lock:
            if key in self._json:
                return self._json[key]
        value = project.store.get_json(ref_id, Zone.VERIFIER)
        with self._lock:
            return self._json.setdefault(key, value)

    def raw(self, project: Project, ref_id: str) -> bytes:
        key = (str(project.dir.resolve()), ref_id)
        with self._lock:
            if key in self._bytes:
                return self._bytes[key]
        value = project.store.get(ref_id, Zone.VERIFIER)
        with self._lock:
            return self._bytes.setdefault(key, value)
