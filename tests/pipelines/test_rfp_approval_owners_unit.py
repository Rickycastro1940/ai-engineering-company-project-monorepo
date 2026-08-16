"""Part 3 unit: CONTEXT §2.1 named owners; no invented org ladder."""

from __future__ import annotations

import pytest

from data.pipelines.rfp_approval.approvers import (
    CEO_NAME,
    InvalidResumeDecisionError,
    UnknownApproverError,
    assert_allowed_approver,
    requires_ceo_approval,
    signoffs_for_ticket,
    validate_human_resume,
)
from data.pipelines.rfp_intake.context_rules import (
    CONTEXT_DEPARTMENT_OWNERS,
    parse_context_arbitration_table,
    required_signoffs,
)


def test_signoffs_are_named_department_owners_only() -> None:
    signoffs = signoffs_for_ticket(
        ["marketing", "operaciones", "procurement"], requires_ceo=False
    )
    names = {s.approver for s in signoffs}
    assert names == {
        "Camila Ospina",
        "Felipe Guerrero",
        "Lucía Fernández",
    }
    assert all(s.role == "department_owner" for s in signoffs)
    assert CEO_NAME not in names


def test_ceo_is_only_extra_approver_when_threshold_met() -> None:
    without = signoffs_for_ticket(["marketing"], requires_ceo=False)
    assert all(s.department_id != "ceo" for s in without)
    with_ceo = signoffs_for_ticket(["marketing"], requires_ceo=True)
    assert with_ceo[-1].department_id == "ceo"
    assert with_ceo[-1].approver == "Mariana Restrepo"
    assert with_ceo[-1].role == "ceo"


def test_unknown_and_invented_titles_are_rejected() -> None:
    with pytest.raises(UnknownApproverError):
        assert_allowed_approver("marketing", "VP of Sales")
    with pytest.raises(UnknownApproverError):
        assert_allowed_approver("marketing", "Legal")
    with pytest.raises(UnknownApproverError):
        assert_allowed_approver("operaciones", "Camila Ospina")
    assert assert_allowed_approver("marketing", "Camila Ospina") == "Camila Ospina"
    assert assert_allowed_approver("ceo", "Mariana Restrepo") == "Mariana Restrepo"


def test_validate_human_resume_accepts_approve_reject_request_changes() -> None:
    approved = validate_human_resume(
        {
            "department_id": "marketing",
            "decision": "approve",
            "approver": "Camila Ospina",
        }
    )
    assert approved["decision"] == "approved"
    assert approved["approver"] == "Camila Ospina"

    rejected = validate_human_resume(
        {
            "department_id": "operaciones",
            "decision": "reject",
            "approver": "Felipe Guerrero",
        }
    )
    assert rejected["decision"] == "rejected"

    changes = validate_human_resume(
        {
            "department_id": "procurement",
            "decision": "request changes",
            "approver": "Lucía Fernández",
        }
    )
    assert changes["decision"] == "request_changes"

    with pytest.raises(InvalidResumeDecisionError, match="approve, reject, or request_changes"):
        validate_human_resume(
            {
                "department_id": "marketing",
                "decision": "maybe",
                "approver": "Camila Ospina",
            }
        )
    with pytest.raises(UnknownApproverError):
        validate_human_resume(
            {
                "department_id": "marketing",
                "decision": "approved",
                "approver": "VP of Sales",
            }
        )


def test_ceo_threshold_uses_context_50000() -> None:
    assert requires_ceo_approval(estimated_contract_value_usd=50_000) is False
    assert requires_ceo_approval(estimated_contract_value_usd=50_000.01) is True
    assert requires_ceo_approval(requires_ceo_flag=True, estimated_contract_value_usd=1) is True
    assert requires_ceo_approval(
        metadata={"estimated_contract_value_usd": 75_000}
    )


def test_required_signoffs_match_context_owners_table() -> None:
    rows = required_signoffs(
        list(CONTEXT_DEPARTMENT_OWNERS), requires_ceo_approval=True
    )
    by_dept = {r["department_id"]: r["approver"] for r in rows}
    assert by_dept["marketing"] == "Camila Ospina"
    assert by_dept["operaciones"] == "Felipe Guerrero"
    assert by_dept["procurement"] == "Lucía Fernández"
    assert by_dept["training"] == "Jake Morrison"
    assert by_dept["ceo"] == "Mariana Restrepo"


def test_context_section_7_lists_three_trigger_ids() -> None:
    rows = parse_context_arbitration_table()
    ids = [r["trigger_id"] for r in rows]
    assert ids == [
        "cost-vs-feasibility",
        "setup-sla-breach",
        "ceo-threshold",
    ]
    arbiters = " ".join(r["arbiter"] for r in rows)
    assert "Camila Ospina" in arbiters
    assert "Felipe Guerrero" in arbiters
    assert "Mariana Restrepo" in arbiters
