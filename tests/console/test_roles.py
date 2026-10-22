"""Approval roles offered by the console (D-010: operator or customer analyst)."""

from typing import get_args

import pytest

from reverseai.barrier.release import Approval
from reverseai.console.roles import CONSOLE_ROLES, approval_role, role_label

ACCEPTED = set(get_args(Approval.model_fields["role"].annotation))


def test_console_offers_operator_and_customer_analyst() -> None:
    assert list(CONSOLE_ROLES) == ["operator", "customer_analyst"]
    assert CONSOLE_ROLES["customer_analyst"] == "Аналитик заказчика"


@pytest.mark.parametrize("role", ["operator", "customer_analyst"])
def test_every_console_role_maps_to_a_role_the_barrier_accepts(role) -> None:
    approval = Approval(approver="A", role=approval_role(role), approved_at="t",
                        package_sha256="0" * 64)
    assert approval.role in ACCEPTED


def test_console_roles_are_recorded_as_is() -> None:
    # D-010: the barrier accepts operator and customer_analyst; the mapping is the identity.
    assert ACCEPTED == {"operator", "customer_analyst"}
    assert approval_role("customer_analyst") == "customer_analyst"
    assert approval_role("operator") == "operator"


def test_unknown_role_is_refused() -> None:
    with pytest.raises(ValueError):
        approval_role("customer_lawyer")


def test_role_labels_for_recorded_roles() -> None:
    assert role_label("operator") == "оператор платформы"
    assert role_label("customer_analyst") == "аналитик заказчика"
    # Old ledgers and packages may still carry the role used before D-010: shown as it was.
    assert role_label("customer_lawyer") == "юрист заказчика (до D-010)"
    assert role_label("bench") == "bench"
