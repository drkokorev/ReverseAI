"""Who may approve a release package at the barrier (D-010).

The console offers the platform operator and the customer analyst; the customer's lawyer does
not act in the pipeline. `approval_role` is the single place where a console role becomes the
role recorded in `Approval`.
"""

from __future__ import annotations

from reverseai.i18n import Labels, t

CONSOLE_ROLES: Labels[str] = Labels("role", ["operator", "customer_analyst"])

# D-010: console role values match `Approval.role` one to one.
_APPROVAL_ROLES: dict[str, str] = {"operator": "operator", "customer_analyst": "customer_analyst"}

# Approvals recorded before D-010 (when the barrier knew a lawyer role) stay readable.
_RECORDED_ROLES = ("operator", "customer_analyst", "customer_lawyer")


def approval_role(role: str) -> str:
    """The `Approval.role` value for a console role; ValueError for anything else."""
    try:
        return _APPROVAL_ROLES[role]
    except KeyError:
        raise ValueError(f"unknown console role {role!r}") from None


def role_label(recorded: str) -> str:
    """Label of a role recorded in an approval (unknown roles are shown as is)."""
    return t(f"role.recorded.{recorded}") if recorded in _RECORDED_ROLES else recorded
