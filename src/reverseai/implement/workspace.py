"""Confined file access for the clean-zone implementation workspace.

Every path an agent proposes goes through ``safe_write``, which refuses anything that could
land outside the workspace root (absolute paths, ``..``, symlinks pointing out).
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

MAX_FILE_BYTES = 500_000
MAX_SNAPSHOT_CHARS = 200_000  # file contents in one executor prompt, all files together
ORACLE_RUNNER = "oracle_runner.py"
ORACLE_SCENARIOS = "oracle_scenarios.json"
ORACLE_FILES = frozenset({ORACLE_RUNNER, ORACLE_SCENARIOS})
_SKIP_DIRS = frozenset({"__pycache__"})


class WorkspaceError(Exception):
    """A proposed workspace edit was refused; nothing was written."""


def _check_rel_path(rel_path: str) -> PurePosixPath:
    if not rel_path or "\x00" in rel_path or "\\" in rel_path:
        raise WorkspaceError("path must be a non-empty relative path using '/' separators")
    path = PurePosixPath(rel_path)
    if path.is_absolute():
        raise WorkspaceError("absolute paths are not allowed")
    if ".." in path.parts:
        raise WorkspaceError("'..' is not allowed in paths")
    if not path.parts:
        raise WorkspaceError("path must name a file inside the workspace")
    return path


def safe_write(root: Path, rel_path: str, content: str) -> Path:
    """Write ``content`` to ``root/rel_path`` if the resolved target stays inside ``root``."""
    path = _check_rel_path(rel_path)
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise WorkspaceError(f"file too large: {len(data)} bytes > {MAX_FILE_BYTES}")
    base = Path(root).resolve()
    target = (base / path).resolve()  # follows symlinks of every existing component
    if target == base or not target.is_relative_to(base):
        raise WorkspaceError("path resolves outside the workspace")
    if target.is_dir():
        raise WorkspaceError("path is a directory")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError as exc:  # e.g. a parent component is an existing file
        raise WorkspaceError(f"cannot write file: {type(exc).__name__}") from exc
    return target


def workspace_files(root: Path) -> list[Path]:
    """Regular files under ``root`` (sorted, relative), skipping oracle files, caches, symlinks."""
    root = Path(root)
    found: list[Path] = []

    def walk(directory: Path) -> None:
        for entry in sorted(directory.iterdir()):
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS:
                    walk(entry)
                continue
            rel = entry.relative_to(root)
            if entry.is_file() and rel.as_posix() not in ORACLE_FILES:
                found.append(rel)

    if root.is_dir():
        walk(root)
    return found


def _read_text(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def snapshot(
    root: Path, max_file_chars: int = 20_000, max_total_chars: int = MAX_SNAPSHOT_CHARS
) -> str:
    """File tree plus the contents of text files, each cut to ``max_file_chars``.

    Contents stop once ``max_total_chars`` are shown; the remaining files stay in the tree
    and are named as not shown, so the executor prompt stays bounded however big the
    workspace grows.
    """
    root = Path(root)
    files = workspace_files(root)
    if not files:
        return "Files:\n(empty)\n"
    lines = ["Files:", *(f"- {rel.as_posix()}" for rel in files), ""]
    budget = max_total_chars
    hidden: list[str] = []
    for rel in files:
        text = _read_text(root / rel)
        if text is None or "\x00" in text:
            continue
        if len(text) > max_file_chars:
            cut = len(text) - max_file_chars
            text = f"{text[:max_file_chars]}\n... [truncated {cut} chars]"
        if len(text) > budget:
            hidden.append(rel.as_posix())
            continue
        budget -= len(text)
        lines.append(f"=== {rel.as_posix()} ===")
        lines.append(text if text.endswith("\n") else text + "\n")
    if hidden:
        lines.append(
            f"(content not shown, snapshot budget of {max_total_chars} chars reached: "
            + ", ".join(hidden)
            + ")\n"
        )
    return "\n".join(lines)
