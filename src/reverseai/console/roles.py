"""Who may approve a release package at the barrier (D-010).

The console offers the platform operator and the customer analyst; the customer's lawyer does
not act in the pipeline. `approval_role` is the single place where a console role becomes the
role recorded in `Approval`.
"""

from __future__ import annotations

CONSOLE_ROLES: dict[str, str] = {
    "operator": "Оператор платформы",
    "customer_analyst": "Аналитик заказчика",
}

# D-010: console role values match `Approval.role` one to one.
_APPROVAL_ROLES: dict[str, str] = {"operator": "operator", "customer_analyst": "customer_analyst"}

_RECORDED_LABELS: dict[str, str] = {
    "operator": "оператор платформы",
    "customer_analyst": "аналитик заказчика",
    # Approvals recorded before D-010 (when the barrier knew a lawyer role) stay readable.
    "customer_lawyer": "юрист заказчика (до D-010)",
}


def approval_role(role: str) -> str:
    """The `Approval.role` value for a console role; ValueError for anything else."""
    try:
        return _APPROVAL_ROLES[role]
    except KeyError:
        raise ValueError(f"unknown console role {role!r}") from None


def role_label(recorded: str) -> str:
    """Russian label of a role recorded in an approval (unknown roles are shown as is)."""
    return _RECORDED_LABELS.get(recorded, recorded)
