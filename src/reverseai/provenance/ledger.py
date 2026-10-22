"""Append-only, hash-chained provenance ledger (one JSON object per line).

Several writers may share one ledger file (the CLI, the web console, two `Ledger` objects):
every append takes an exclusive lock on a sidecar `<ledger>.lock` file, re-reads the last
valid event from disk and only then chains to it, so the hash chain never forks.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:  # POSIX; elsewhere only the in-process lock applies
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

GENESIS_HASH = "0" * 64
_TAIL_BLOCK = 65_536
_FIELDS = ("seq", "ts", "type", "zone", "actor", "payload", "prev_hash", "hash")


@dataclass(frozen=True)
class LedgerEvent:
    seq: int
    ts: str
    type: str
    zone: str
    actor: str
    payload: dict
    prev_hash: str
    hash: str


@dataclass(frozen=True)
class LedgerVerification:
    ok: bool
    count: int
    broken_at: int | None = None
    reason: str | None = None


def _compute_hash(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_hash(event: LedgerEvent) -> str:
    body = asdict(event)
    del body["hash"]
    return _compute_hash(body)


def _parse_line(line: bytes) -> LedgerEvent:
    obj = json.loads(line.decode("utf-8"))
    if not isinstance(obj, dict) or set(obj) != set(_FIELDS):
        raise ValueError("unexpected fields")
    if not isinstance(obj["seq"], int) or isinstance(obj["seq"], bool):
        raise TypeError("seq is not an integer")
    if not isinstance(obj["payload"], dict):
        raise TypeError("payload is not an object")
    return LedgerEvent(**obj)


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _lines(self) -> list[bytes]:
        # Split on b"\n" only: str.splitlines() would also split on U+2028/U+2029/U+0085,
        # which json.dumps(ensure_ascii=False) leaves unescaped inside strings.
        if not self.path.exists():
            return []
        return [ln for ln in self.path.read_bytes().split(b"\n") if ln.strip()]

    def _read_valid(self) -> list[LedgerEvent]:
        """All parseable events; unparseable lines (crash residue) are skipped."""
        events: list[LedgerEvent] = []
        for line in self._lines():
            try:
                events.append(_parse_line(line))
            except (ValueError, TypeError):
                continue
        return events

    def _last_valid(self) -> LedgerEvent | None:
        """The last parseable event on disk, read backwards from the end of the file."""
        if not self.path.exists():
            return None
        with self.path.open("rb") as f:
            pos = f.seek(0, os.SEEK_END)
            carry = b""
            while pos > 0:
                size = min(_TAIL_BLOCK, pos)
                pos -= size
                f.seek(pos)
                lines = (f.read(size) + carry).split(b"\n")
                carry = lines.pop(0) if pos > 0 else b""  # may be cut: finish it next round
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        return _parse_line(line)
                    except (ValueError, TypeError):
                        continue
        return None

    @contextlib.contextmanager
    def _exclusive(self):
        """This process's threads and every other process: one appender at a time."""
        with self._lock:
            if fcntl is None:  # pragma: no cover
                yield
                return
            with self._lock_path.open("ab") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def append(self, type: str, zone: str, actor: str, payload: dict) -> LedgerEvent:
        with self._exclusive():
            last = self._last_valid()  # another writer may have appended since our last write
            body = {
                "seq": last.seq + 1 if last is not None else 0,
                "ts": datetime.now(UTC).isoformat(),
                "type": type,
                "zone": zone,
                "actor": actor,
                "payload": payload,
                "prev_hash": last.hash if last is not None else GENESIS_HASH,
            }
            event = LedgerEvent(**body, hash=_compute_hash(body))
            line = json.dumps(asdict(event), ensure_ascii=False) + "\n"
            with self.path.open("ab") as f:
                if f.tell() > 0:
                    with self.path.open("rb") as r:
                        r.seek(-1, os.SEEK_END)
                        if r.read(1) != b"\n":
                            f.write(b"\n")  # isolate crash residue on its own line
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            return event

    def events(self) -> list[LedgerEvent]:
        with self._lock:
            return self._read_valid()

    def verify(self) -> LedgerVerification:
        with self._lock:
            lines = self._lines()
        prev = GENESIS_HASH
        for index, line in enumerate(lines):
            try:
                event = _parse_line(line)
            except (ValueError, TypeError) as exc:
                return LedgerVerification(False, index, index, f"cannot parse line: {exc}")
            if event.seq != index:
                return LedgerVerification(
                    False, index, index, f"seq mismatch: expected {index}, got {event.seq}"
                )
            if event.prev_hash != prev:
                return LedgerVerification(False, index, index, "prev_hash does not match chain")
            if _event_hash(event) != event.hash:
                return LedgerVerification(False, index, index, "hash mismatch (line was modified)")
            prev = event.hash
        return LedgerVerification(True, len(lines))
