"""Data policy: which provider jurisdictions may receive project data."""

from __future__ import annotations

from dataclasses import dataclass, field


class PolicyViolation(Exception):
    """Raised when a call would send data to a disallowed jurisdiction."""


@dataclass
class DataPolicy:
    allowed_jurisdictions: set[str] = field(default_factory=lambda: {"us", "eu", "self"})
