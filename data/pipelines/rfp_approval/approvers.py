"""CONTEXT §2.1 / §6 Part 3 sign-off roster.

Each *active* department is signed off by its named owner. The only extra
approver CONTEXT names is Mariana Restrepo (CEO) when estimated annual value
exceeds $50,000 USD. Do not invent a multi-level org ladder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_CEO_DEPARTMENT_ID,
    CONTEXT_CEO_NAME,
    CONTEXT_CEO_USD_THRESHOLD,
    CONTEXT_DEPARTMENT_IDS,
    CONTEXT_DEPARTMENT_OWNERS,
    CONTEXT_FORBIDDEN_EXTRA_APPROVERS,
    CONTEXT_TICKET_OWNER,
    required_signoffs,
)

CEO_DEPARTMENT_ID: Final = CONTEXT_CEO_DEPARTMENT_ID
CEO_NAME: Final = CONTEXT_CEO_NAME
CEO_USD_THRESHOLD: Final = CONTEXT_CEO_USD_THRESHOLD
DEPARTMENT_OWNERS: Final = dict(CONTEXT_DEPARTMENT_OWNERS)
TICKET_OWNER: Final = CONTEXT_TICKET_OWNER

ALLOWED_DECISIONS: Final[frozenset[str]] = frozenset(
    {"approved", "rejected", "request_changes"}
)


class UnknownApproverError(ValueError):
    """Raised when a signer is not the CONTEXT-named owner (or CEO)."""


@dataclass(frozen=True)
class Signoff:
    department_id: str
    approver: str
    role: str  # department_owner | ceo

    def to_dict(self) -> dict[str, str]:
        return {
            "department_id": self.department_id,
            "approver": self.approver,
            "role": self.role,
        }


def _norm(name: str) -> str:
    return " ".join((name or "").strip().casefold().split())


def requires_ceo_approval(
    *,
    requires_ceo_flag: bool | None = None,
    estimated_contract_value_usd: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """CEO extra approval only when CONTEXT §5 / §6 threshold is met."""
    if requires_ceo_flag:
        return True
    meta = metadata or {}
    if meta.get("requires_ceo_approval"):
        return True
    value = estimated_contract_value_usd
    if value is None:
        value = meta.get("estimated_contract_value_usd")
    if value is None:
        return False
    try:
        return float(value) > CEO_USD_THRESHOLD
    except (TypeError, ValueError):
        return False


def signoffs_for_ticket(
    departments_needed: list[str],
    *,
    requires_ceo: bool,
) -> list[Signoff]:
    rows = required_signoffs(list(departments_needed), requires_ceo_approval=requires_ceo)
    return [Signoff(**row) for row in rows]


def expected_approver(department_id: str) -> str:
    if department_id == CEO_DEPARTMENT_ID:
        return CEO_NAME
    owner = DEPARTMENT_OWNERS.get(department_id)
    if not owner:
        raise UnknownApproverError(
            f"No CONTEXT §2.1 owner for department {department_id!r}; "
            f"expected one of {sorted(CONTEXT_DEPARTMENT_IDS)}"
        )
    return owner


def assert_allowed_approver(department_id: str, approver: str) -> str:
    """Reject invented titles; require the named CONTEXT owner (or CEO)."""
    name = (approver or "").strip()
    if not name:
        raise UnknownApproverError("Approver name is required")
    folded = _norm(name)
    if folded in CONTEXT_FORBIDDEN_EXTRA_APPROVERS:
        raise UnknownApproverError(
            f"{name!r} is not a CONTEXT approver — sign-off is the named "
            f"department owner (and CEO {CEO_NAME} only when >"
            f"${CEO_USD_THRESHOLD:,.0f} USD/year)"
        )
    expected = expected_approver(department_id)
    if _norm(expected) != folded:
        raise UnknownApproverError(
            f"{name!r} cannot sign off {department_id!r}; CONTEXT requires {expected}"
        )
    return expected


def normalize_decision(decision: str) -> str:
    raw = (decision or "").strip().casefold().replace(" ", "_")
    aliases = {
        "approve": "approved",
        "approved": "approved",
        "reject": "rejected",
        "rejected": "rejected",
        "request_changes": "request_changes",
        "request-changes": "request_changes",
        "changes_requested": "request_changes",
    }
    mapped = aliases.get(raw, raw)
    if mapped not in ALLOWED_DECISIONS:
        raise ValueError(
            f"Unknown decision {decision!r}; expected one of {sorted(ALLOWED_DECISIONS)}"
        )
    return mapped
