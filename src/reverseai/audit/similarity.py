"""Code similarity against the original's expression, and brand-term mentions in clone code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from reverseai.barrier.sanitizer import has_brand, tokenize

TEXT_SUFFIXES = frozenset({".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".md"})


@dataclass(frozen=True)
class SimilarityReport:
    threshold: float
    max_score: float
    per_file: dict[str, float]
    ok: bool


def _shingles(text: str, size: int) -> set[tuple[str, ...]]:
    tokens = tokenize(text)
    return {tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def _is_text(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in TEXT_SUFFIXES


def code_similarity(
    code_files: dict[str, str],
    expression_texts: list[str],
    *,
    shingle: int = 8,
    threshold: float = 0.05,
) -> SimilarityReport:
    """Containment of each clone file's token shingles in the original's shingles."""
    corpus: set[tuple[str, ...]] = set()
    for text in expression_texts:
        corpus |= _shingles(text, shingle)
    per_file: dict[str, float] = {}
    for path, text in code_files.items():
        if not _is_text(path):
            continue
        own = _shingles(text, shingle)
        per_file[path] = len(own & corpus) / len(own) if own else 0.0
    max_score = max(per_file.values(), default=0.0)
    return SimilarityReport(threshold, max_score, per_file, max_score < threshold)


def brand_mentions(code_files: dict[str, str], brand_terms: list[str]) -> list[str]:
    """``"path:line"`` for every line that mentions a brand term.

    The barrier's rule (``has_brand``): case-insensitive, words joined by spaces, ``_``, ``-``
    or nothing, also inside identifiers (``acme_id``, ``AcmeTasks``), never inside other words.
    """
    terms = [term for term in brand_terms if term.strip()]
    hits: list[str] = []
    for path, text in code_files.items():
        if not _is_text(path) or not terms:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if has_brand(line, terms):
                hits.append(f"{path}:{number}")
    return hits
