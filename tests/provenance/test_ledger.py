import json
import threading
from datetime import UTC, datetime

from reverseai.provenance.ledger import Ledger

GENESIS = "0" * 64


def test_chain_links(tmp_path):
    l = Ledger(tmp_path / "l.jsonl")
    a = l.append("x", "dirty", "test", {"k": 1})
    b = l.append("y", "clean", "test", {})
    assert a.seq == 0 and b.seq == 1 and b.prev_hash == a.hash
    assert a.prev_hash == GENESIS
    assert l.verify().ok and l.verify().count == 2
    assert l.events() == [a, b]


def test_timestamp_is_utc_iso8601(tmp_path):
    ev = Ledger(tmp_path / "l.jsonl").append("x", "dirty", "test", {})
    parsed = datetime.fromisoformat(ev.ts)
    assert parsed.utcoffset() == UTC.utcoffset(None)


def test_empty_ledger_verifies(tmp_path):
    l = Ledger(tmp_path / "l.jsonl")
    v = l.verify()
    assert v.ok and v.count == 0 and v.broken_at is None and v.reason is None
    assert l.events() == []


def test_one_json_object_per_line_with_canonical_hash(tmp_path):
    import hashlib

    path = tmp_path / "l.jsonl"
    l = Ledger(path)
    ev = l.append("x", "dirty", "тест", {"b": 1, "a": "é"})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    body = {k: v for k, v in obj.items() if k != "hash"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canon.encode("utf-8")).hexdigest() == ev.hash == obj["hash"]


def test_reopen_continues_chain(tmp_path):
    path = tmp_path / "l.jsonl"
    l1 = Ledger(path)
    l1.append("x", "dirty", "test", {})
    last = l1.append("y", "dirty", "test", {})
    l2 = Ledger(path)
    nxt = l2.append("z", "clean", "test", {})
    assert nxt.seq == 2 and nxt.prev_hash == last.hash
    assert l2.verify().ok and l2.verify().count == 3


def test_creates_parent_dirs(tmp_path):
    l = Ledger(tmp_path / "a" / "b" / "l.jsonl")
    l.append("x", "dirty", "test", {})
    assert l.verify().ok


def test_tampered_middle_line_detected(tmp_path):
    path = tmp_path / "l.jsonl"
    l = Ledger(path)
    for i in range(3):
        l.append("x", "dirty", "test", {"i": i})
    lines = path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[1])
    obj["payload"] = {"i": 999}
    lines[1] = json.dumps(obj)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = l.verify()
    assert v.ok is False and v.broken_at == 1 and v.reason


def test_rehashed_tampered_line_breaks_next_link(tmp_path):
    import hashlib

    path = tmp_path / "l.jsonl"
    l = Ledger(path)
    for i in range(3):
        l.append("x", "dirty", "test", {"i": i})
    lines = path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[1])
    obj["payload"] = {"i": 999}
    body = {k: v for k, v in obj.items() if k != "hash"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    obj["hash"] = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    lines[1] = json.dumps(obj)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = l.verify()
    assert v.ok is False and v.broken_at == 2


def test_truncated_last_line_reported_not_raised(tmp_path):
    path = tmp_path / "l.jsonl"
    l = Ledger(path)
    l.append("x", "dirty", "test", {})
    l.append("y", "dirty", "test", {})
    with path.open("a", encoding="utf-8") as f:
        f.write('{"seq":2,"ts":"2026-')
    v = l.verify()
    assert v.ok is False and v.broken_at == 2 and "parse" in v.reason
    assert len(l.events()) == 2


def test_reopen_after_truncated_tail_continues_from_last_valid(tmp_path):
    path = tmp_path / "l.jsonl"
    l = Ledger(path)
    l.append("x", "dirty", "test", {})
    last = l.append("y", "dirty", "test", {})
    with path.open("a", encoding="utf-8") as f:
        f.write('{"seq":2,"ts":"2026-')
    l2 = Ledger(path)
    nxt = l2.append("z", "dirty", "test", {})
    assert nxt.seq == 2 and nxt.prev_hash == last.hash
    # the crash residue stays visible: the chain is still reported as broken
    assert l2.verify().ok is False


def test_concurrent_appends_keep_chain_valid(tmp_path):
    l = Ledger(tmp_path / "l.jsonl")

    def work():
        for _ in range(25):
            l.append("x", "dirty", "t", {})

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    v = l.verify()
    assert v.ok and v.count == 200
    assert [e.seq for e in l.events()] == list(range(200))


def test_truncated_multibyte_tail_reported_not_raised(tmp_path):
    path = tmp_path / "l.jsonl"
    l = Ledger(path)
    l.append("x", "dirty", "test", {"t": "привет"})
    l.append("y", "dirty", "test", {})
    with path.open("ab") as f:
        f.write('{"seq":2,"payload":{"t":"при'.encode()[:-1])  # cut inside a Cyrillic char
    v = l.verify()
    assert v.ok is False and v.broken_at == 2 and "parse" in v.reason
    assert len(l.events()) == 2
    reopened = Ledger(path)  # constructor must not raise either
    assert reopened.append("z", "dirty", "test", {}).seq == 2


def test_unicode_line_separators_in_payload(tmp_path):
    path = tmp_path / "l.jsonl"
    l = Ledger(path)
    a = l.append("x", "dirty", "test", {"t": "a b c\u0085d"})
    assert l.verify().ok and l.verify().count == 1
    assert l.events() == [a]
    b = Ledger(path).append("y", "dirty", "test", {})
    assert b.seq == 1 and b.prev_hash == a.hash
    assert Ledger(path).verify().ok


def test_events_after_residue_survive_two_reopens(tmp_path):
    path = tmp_path / "l.jsonl"
    l = Ledger(path)
    l.append("x", "dirty", "test", {})
    l.append("y", "dirty", "test", {})
    with path.open("a", encoding="utf-8") as f:
        f.write('{"seq":2,"ts":"2026-')
    c = Ledger(path).append("z", "dirty", "test", {})
    d = Ledger(path).append("w", "dirty", "test", {})
    assert (c.seq, d.seq) == (2, 3) and d.prev_hash == c.hash
    events = Ledger(path).events()
    assert [e.seq for e in events] == [0, 1, 2, 3]
    v = Ledger(path).verify()
    assert v.ok is False and v.broken_at == 2


def test_two_ledger_objects_on_one_file_keep_one_chain(tmp_path):
    path = tmp_path / "l.jsonl"
    a, b = Ledger(path), Ledger(path)
    for i in range(10):
        (a if i % 2 == 0 else b).append("x", "dirty", "t", {"i": i})
    v = Ledger(path).verify()
    assert v.ok and v.count == 10
    assert [e.seq for e in Ledger(path).events()] == list(range(10))


def test_two_processes_appending_keep_one_chain(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "l.jsonl"
    Ledger(path).append("start", "dirty", "t", {})
    script = (
        "import sys\n"
        "from reverseai.provenance.ledger import Ledger\n"
        "ledger = Ledger(sys.argv[1])\n"
        "for i in range(50):\n"
        "    ledger.append('x', 'dirty', sys.argv[2], {'i': i})\n"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", script, str(path), f"p{n}"]) for n in range(2)
    ]
    assert [p.wait(timeout=120) for p in procs] == [0, 0]
    v = Ledger(path).verify()
    assert v.ok, v.reason
    assert v.count == 101
    seqs = [e.seq for e in Ledger(path).events()]
    assert seqs == list(range(101))
