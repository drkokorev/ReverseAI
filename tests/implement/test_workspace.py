import pytest

from reverseai.implement.workspace import (
    MAX_FILE_BYTES,
    WorkspaceError,
    safe_write,
    snapshot,
)


def _files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def test_safe_write_creates_nested_file(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    path = safe_write(root, "pkg/sub/mod.py", "x = 1\n")
    assert path == (root / "pkg/sub/mod.py").resolve()
    assert path.read_text(encoding="utf-8") == "x = 1\n"


def test_safe_write_overwrites_existing_file(tmp_path):
    safe_write(tmp_path, "main.py", "old")
    safe_write(tmp_path, "main.py", "new")
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "new"


@pytest.mark.parametrize("bad", ["../x.py", "/etc/passwd", "a/../../x"])
def test_safe_write_rejects_escape(tmp_path, bad):
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(WorkspaceError):
        safe_write(root, bad, "pwned")
    assert _files(root) == []
    assert not (tmp_path / "x.py").exists()
    assert not (tmp_path / "x").exists()


@pytest.mark.parametrize("bad", ["", ".", "a/./b/..", "a/..", "C:\\x.py", "a\\..\\..\\x", "a\x00b"])
def test_safe_write_rejects_degenerate_paths(tmp_path, bad):
    with pytest.raises(WorkspaceError):
        safe_write(tmp_path, bad, "x")
    assert _files(tmp_path) == []


def test_safe_write_rejects_symlink_escape(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    (outside / "victim.py").write_text("original", encoding="utf-8")
    (root / "victim.py").symlink_to(outside / "victim.py")

    with pytest.raises(WorkspaceError):
        safe_write(root, "link/x.py", "pwned")
    with pytest.raises(WorkspaceError):
        safe_write(root, "victim.py", "pwned")

    assert not (outside / "x.py").exists()
    assert (outside / "victim.py").read_text(encoding="utf-8") == "original"


def test_safe_write_rejects_dangling_symlink_out(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "new.py").symlink_to(tmp_path / "missing" / "new.py")
    with pytest.raises(WorkspaceError):
        safe_write(root, "new.py", "pwned")
    assert not (tmp_path / "missing").exists()


def test_safe_write_reports_os_errors_as_workspace_errors(tmp_path):
    safe_write(tmp_path, "main.py", "x")
    with pytest.raises(WorkspaceError):
        safe_write(tmp_path, "main.py/inner.py", "x")
    safe_write(tmp_path, "pkg/mod.py", "x")
    with pytest.raises(WorkspaceError, match="directory"):
        safe_write(tmp_path, "pkg", "x")


def test_safe_write_rejects_oversized_content(tmp_path):
    safe_write(tmp_path, "ok.txt", "a" * MAX_FILE_BYTES)
    with pytest.raises(WorkspaceError, match="too large"):
        safe_write(tmp_path, "big.txt", "a" * (MAX_FILE_BYTES + 1))
    # size is measured in UTF-8 bytes, not characters
    with pytest.raises(WorkspaceError, match="too large"):
        safe_write(tmp_path, "wide.txt", "я" * (MAX_FILE_BYTES // 2 + 1))
    assert not (tmp_path / "big.txt").exists()
    assert not (tmp_path / "wide.txt").exists()


def test_snapshot_lists_tree_and_text_contents(tmp_path):
    safe_write(tmp_path, "main.py", "print('hi')\n")
    safe_write(tmp_path, "app/routes.py", "ROUTES = []\n")
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    snap = snapshot(tmp_path)
    assert "- main.py" in snap
    assert "- app/routes.py" in snap
    assert "- blob.bin" in snap
    assert "=== main.py ===\nprint('hi')\n" in snap
    assert "=== app/routes.py ===\nROUTES = []\n" in snap
    assert "=== blob.bin ===" not in snap


def test_snapshot_skips_oracle_files_pycache_and_symlinks(tmp_path):
    safe_write(tmp_path, "main.py", "app = 1\n")
    safe_write(tmp_path, "oracle_runner.py", "RUNNER SOURCE\n")
    safe_write(tmp_path, "oracle_scenarios.json", '["SCENARIOS"]')
    safe_write(tmp_path, "__pycache__/main.cpython-312.pyc", "BYTECODE")
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("HOST SECRET", encoding="utf-8")
    (tmp_path / "leak.txt").symlink_to(secret)

    snap = snapshot(tmp_path)
    assert "main.py" in snap
    for hidden in ("oracle_runner", "RUNNER SOURCE", "SCENARIOS", "__pycache__", "BYTECODE",
                   "leak.txt", "HOST SECRET"):
        assert hidden not in snap


def test_snapshot_truncates_long_files(tmp_path):
    safe_write(tmp_path, "long.py", "a" * 50 + "TAIL")
    snap = snapshot(tmp_path, max_file_chars=50)
    assert "a" * 50 in snap
    assert "TAIL" not in snap
    assert "[truncated 4 chars]" in snap


def test_snapshot_of_empty_workspace(tmp_path):
    assert "(empty)" in snapshot(tmp_path)


def test_snapshot_has_a_total_budget(tmp_path):
    for i in range(30):
        (tmp_path / f"m{i:02d}.py").write_text("x" * 20_000 + "\n")
    snap = snapshot(tmp_path, max_total_chars=100_000)
    assert len(snap) < 100_000 + 5_000  # tree listing and notes on top of the budget
    for i in range(30):
        assert f"- m{i:02d}.py" in snap  # every file is still listed
    shown = [i for i in range(30) if f"=== m{i:02d}.py ===" in snap]
    assert shown and len(shown) < 30
    assert "content not shown" in snap


def test_snapshot_default_budget_bounds_the_prompt(tmp_path):
    from reverseai.implement.workspace import MAX_SNAPSHOT_CHARS

    for i in range(60):
        (tmp_path / f"m{i:02d}.py").write_text("y" * 20_000 + "\n")
    assert len(snapshot(tmp_path)) < MAX_SNAPSHOT_CHARS + 10_000
