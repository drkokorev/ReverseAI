import hashlib
import threading

import pytest

from reverseai.provenance.ledger import Ledger
from reverseai.zones.store import READ_RULES, ArtifactStore, Zone, ZoneViolation


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(tmp_path / "artifacts", Ledger(tmp_path / "ledger.jsonl"))


def test_read_rules_table():
    assert READ_RULES[Zone.DIRTY] == {Zone.DIRTY, Zone.RELEASED}
    assert READ_RULES[Zone.RELEASED] == {Zone.RELEASED}
    assert READ_RULES[Zone.CLEAN] == {Zone.CLEAN, Zone.RELEASED}
    assert READ_RULES[Zone.VERIFIER] == set(Zone)


def test_put_returns_content_addressed_ref(store):
    r = store.put(Zone.DIRTY, "expression", "app.js", b"function a(){}", {"url": "x"})
    assert r.id == hashlib.sha256(b"function a(){}").hexdigest()
    assert (r.zone, r.kind, r.name, r.size, r.meta) == (
        Zone.DIRTY, "expression", "app.js", 14, {"url": "x"},
    )
    assert store.ref(r.id) == r


def test_clean_cannot_read_dirty(store):
    r = store.put(Zone.DIRTY, "expression", "app.js", b"function a(){}")
    with pytest.raises(ZoneViolation):
        store.get(r.id, Zone.CLEAN)
    last = store.ledger.events()[-1]
    assert last.type == "zone.violation"
    assert last.payload["id"] == r.id and last.payload["reader"] == "clean"
    assert last.payload["zone"] == "dirty"


def test_clean_reads_released(store):
    r = store.put(Zone.RELEASED, "release_package", "pkg.json", b"{}")
    assert store.get(r.id, Zone.CLEAN) == b"{}"
    last = store.ledger.events()[-1]
    assert last.type == "artifact.read"
    assert last.payload == {
        "id": r.id, "kind": "release_package", "zone": "released", "reader": "clean",
    }


def test_clean_reads_clean_and_dirty_reads_released(store):
    c = store.put(Zone.CLEAN, "code", "a.py", b"x=1")
    r = store.put(Zone.RELEASED, "release_package", "p.json", b"{}")
    assert store.get(c.id, Zone.CLEAN) == b"x=1"
    assert store.get(r.id, Zone.DIRTY) == b"{}"


def test_dirty_cannot_read_clean_and_released_only_self(store):
    c = store.put(Zone.CLEAN, "code", "a.py", b"x=1")
    d = store.put(Zone.DIRTY, "expression", "a.js", b"y")
    with pytest.raises(ZoneViolation):
        store.get(c.id, Zone.DIRTY)
    with pytest.raises(ZoneViolation):
        store.get(d.id, Zone.RELEASED)


def test_verifier_reads_all(store):
    refs = [store.put(z, "k", "n", z.value.encode()) for z in Zone]
    for r in refs:
        assert store.get(r.id, Zone.VERIFIER) == r.zone.value.encode()


def test_reader_may_be_given_as_string(store):
    r = store.put(Zone.RELEASED, "k", "n", b"z")
    assert store.get(r.id, "clean") == b"z"


def test_same_content_in_two_zones_has_two_entries(store):
    d = store.put(Zone.DIRTY, "k", "n", b"same")
    c = store.put(Zone.CLEAN, "k", "n", b"same")
    assert d.id == c.id and d.zone != c.zone
    assert len(store.list()) == 2
    # clean reader gets the clean entry; the dirty entry never matters to it
    assert store.get(d.id, Zone.CLEAN) == b"same"
    assert store.ref(d.id, Zone.CLEAN).zone == Zone.CLEAN
    assert store.ref(d.id, Zone.DIRTY).zone == Zone.DIRTY


def test_same_content_same_zone_is_one_entry(store):
    a = store.put(Zone.DIRTY, "k", "n", b"same")
    b = store.put(Zone.DIRTY, "k", "n", b"same")
    assert a == b and len(store.list()) == 1


def test_clean_cannot_read_dirty_even_if_content_also_exists_clean_under_other_id(store):
    store.put(Zone.CLEAN, "k", "n", b"other")
    d = store.put(Zone.DIRTY, "k", "n", b"secret")
    with pytest.raises(ZoneViolation):
        store.get(d.id, Zone.CLEAN)


def test_unknown_id_raises_keyerror_and_never_touches_filesystem(store, tmp_path):
    (tmp_path / "artifacts" / "outside").write_bytes(b"leak")
    for bad in ("0" * 64, "../outside", "/etc/passwd", "dirty/../../x"):
        with pytest.raises(KeyError):
            store.get(bad, Zone.VERIFIER)
        with pytest.raises(KeyError):
            store.ref(bad)


def test_name_with_path_separators_is_safe(store, tmp_path):
    r = store.put(Zone.DIRTY, "k", "../../evil.js", b"x")
    assert store.get(r.id, Zone.DIRTY) == b"x"
    assert not (tmp_path / "evil.js").exists()


def test_tampered_content_is_detected(store, tmp_path):
    r = store.put(Zone.DIRTY, "k", "n", b"original")
    (tmp_path / "artifacts" / "dirty" / r.id).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        store.get(r.id, Zone.DIRTY)


def test_put_logs_event_without_content(store):
    r = store.put(Zone.DIRTY, "expression", "app.js", b"SECRET-BODY")
    ev = store.ledger.events()[-1]
    assert ev.type == "artifact.put" and ev.zone == "dirty"
    assert ev.payload["id"] == r.id and ev.payload["kind"] == "expression"
    assert "SECRET-BODY" not in str(ev.payload)


def test_list_filters_by_zone_and_kind(store):
    a = store.put(Zone.DIRTY, "expression", "a.js", b"1")
    b = store.put(Zone.DIRTY, "trace", "t.json", b"2")
    c = store.put(Zone.CLEAN, "expression", "c.py", b"3")
    assert store.list() == [a, b, c]
    assert store.list(zone=Zone.DIRTY) == [a, b]
    assert store.list(kind="expression") == [a, c]
    assert store.list(zone=Zone.CLEAN, kind="expression") == [c]
    assert store.list(zone=Zone.RELEASED) == []


def test_index_survives_reopen(tmp_path):
    root, lp = tmp_path / "a", tmp_path / "l.jsonl"
    s1 = ArtifactStore(root, Ledger(lp))
    r = s1.put(Zone.RELEASED, "k", "n", b"hello", {"m": 1})
    s2 = ArtifactStore(root, Ledger(lp))
    assert s2.list() == [r]
    assert s2.get(r.id, Zone.CLEAN) == b"hello"


def test_index_tolerates_crash_residue(tmp_path):
    root, lp = tmp_path / "a", tmp_path / "l.jsonl"
    s1 = ArtifactStore(root, Ledger(lp))
    r = s1.put(Zone.DIRTY, "k", "n", b"hello")
    with (root / "index.jsonl").open("ab") as f:
        f.write(b'{"id": "abc", "zone": "dir')  # truncated, no newline
    s2 = ArtifactStore(root, Ledger(lp))
    assert s2.list() == [r]
    r2 = s2.put(Zone.DIRTY, "k", "n2", b"world")
    assert ArtifactStore(root, Ledger(lp)).list() == [r, r2]


def test_json_helpers_roundtrip_unicode(store):
    obj = {"имя": "значение", "n": [1, 2]}
    r = store.put_json(Zone.CLEAN, "spec", "s.json", obj)
    assert store.get_json(r.id, Zone.CLEAN) == obj
    assert "значение".encode() in store.get(r.id, Zone.CLEAN)
    d = store.put_json(Zone.DIRTY, "spec", "d.json", {"a": 1})
    with pytest.raises(ZoneViolation):
        store.get_json(d.id, Zone.CLEAN)


def test_concurrent_puts_keep_index_consistent(tmp_path):
    root, lp = tmp_path / "a", tmp_path / "l.jsonl"
    s = ArtifactStore(root, Ledger(lp))
    ts = [
        threading.Thread(target=s.put, args=(Zone.DIRTY, "k", f"n{i}", f"c{i}".encode()))
        for i in range(20)
    ]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(ArtifactStore(root, Ledger(lp)).list()) == 20


def test_same_content_under_another_kind_or_name_keeps_its_own_entry(tmp_path):
    root, lp = tmp_path / "a", tmp_path / "l.jsonl"
    store = ArtifactStore(root, Ledger(lp))
    probes = store.put(Zone.DIRTY, "probe_exchanges", "probe_exchanges", b"[]")
    dropped = store.put(Zone.DIRTY, "oracle_unstable", "oracle_unstable", b"[]", {"m": 1})
    page_a = store.put(Zone.DIRTY, "page", "https://x/a", b"<same page>")
    page_b = store.put(Zone.DIRTY, "page", "https://x/b", b"<same page>")
    assert probes.id == dropped.id
    assert (dropped.kind, dropped.name, dropped.meta) == ("oracle_unstable", "oracle_unstable",
                                                          {"m": 1})
    assert store.list(Zone.DIRTY, "oracle_unstable") == [dropped]
    assert store.list(Zone.DIRTY, "probe_exchanges") == [probes]
    assert [r.name for r in store.list(Zone.DIRTY, "page")] == ["https://x/a", "https://x/b"]
    assert page_a.id == page_b.id
    assert store.ref(dropped.id, Zone.DIRTY, kind="oracle_unstable") == dropped
    assert store.put(Zone.DIRTY, "page", "https://x/a", b"<same page>") == page_a
    assert len(store.list()) == 4
    assert ArtifactStore(root, Ledger(lp)).list() == store.list()


def test_a_second_store_on_the_same_root_sees_new_artifacts(tmp_path):
    root, lp = tmp_path / "a", tmp_path / "l.jsonl"
    first, second = ArtifactStore(root, Ledger(lp)), ArtifactStore(root, Ledger(lp))
    ref = first.put(Zone.RELEASED, "release_package", "r", b"pkg")
    assert second.get(ref.id, Zone.CLEAN) == b"pkg"
    assert second.list(Zone.RELEASED) == [ref]
    assert second.ref(ref.id) == ref
    again = second.put(Zone.RELEASED, "release_package", "r", b"pkg")
    assert again == ref and len(ArtifactStore(root, Ledger(lp)).list()) == 1
