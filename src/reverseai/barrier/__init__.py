"""Clean-room barrier: the only path from the dirty zone to the clean zone."""

from reverseai.barrier.release import (
    Approval,
    PreparedRelease,
    ReleaseError,
    expression_index,
    prepare_release,
    release,
    target_domains,
)
from reverseai.barrier.sanitizer import (
    ExpressionIndex,
    Finding,
    SanitizeReport,
    build_expression_index,
    mask_identifier,
    release_scenarios,
    sanitize_spec,
    sanitize_text,
    tokenize,
)

__all__ = [
    "Approval",
    "ExpressionIndex",
    "Finding",
    "PreparedRelease",
    "ReleaseError",
    "SanitizeReport",
    "build_expression_index",
    "expression_index",
    "mask_identifier",
    "prepare_release",
    "release",
    "release_scenarios",
    "sanitize_spec",
    "sanitize_text",
    "target_domains",
    "tokenize",
]
