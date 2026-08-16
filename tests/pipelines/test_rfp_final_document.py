"""Part 3 unit: FinalDocument only after independent owner (+ CEO) sign-off."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_approval import run_approval_pipeline
from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_approval.checkpointer import reset_approval_checkpointer
from data.pipelines.rfp_approval.synthesizer import synthesizer_ready
from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_WAITING_FOR_APPROVAL,
)


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "final-doc.sqlite"))
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()

SECTIONS = [
    {
        "department_id": "marketing",
        "owner": "Camila Ospina",
        "draft_content": "## Brand terms\nOffer validity period: 30 days from issuance.\n",
    },
    {
        "department_id": "operaciones",
        "owner": "Felipe Guerrero",
        "draft_content": "## Setup times\nSetup in 12 business days.\n## Cost per event\nUSD $40.\n",
    },
    {
        "department_id": "procurement",
        "owner": "Lucía Fernández",
        "draft_content": "## Estimated ingredient cost based on volume\nUSD $20.\n",
    },
]


def _approve_all(departments: list[str]) -> list[dict[str, str]]:
    return [
        {
            "department_id": dept,
            "decision": "approved",
            "approver": DEPARTMENT_OWNERS[dept],
        }
        for dept in departments
    ]


def test_synthesizer_ready_requires_every_active_owner() -> None:
    ready, reason = synthesizer_ready(
        department_approvals={"marketing": "approved", "operaciones": "pending"},
        departments_needed=["marketing", "operaciones"],
        requires_ceo=False,
        ceo_approval_status=None,
    )
    assert ready is False
    assert "operaciones" in reason


def test_andes_all_owners_approve_produces_final_document() -> None:
    depts = ["marketing", "operaciones", "procurement"]
    result = run_approval_pipeline(
        ticket_id="andes-approve",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=SECTIONS,
        metadata={
            "client_name": "Andes Tech Solutions",
            "location": "Medellín",
            "estimated_contract_value_usd": 20_000,
        },
        departments_needed=depts,
        requires_ceo_approval=False,
        queued_decisions=_approve_all(depts),
    )
    assert result.status == STATUS_DONE
    doc = result.final_document
    assert doc["ticket_id"] == "andes-approve"
    assert "sections" in doc
    assert doc["total_estimated_value"] == 20_000
    assert doc.get("generated_at")
    assert doc.get("completion") == "consolidated_approved_sections"
    assert "Andes Tech" in doc["markdown"]
    assert "30 days from issuance" in doc["markdown"]
    assert "consistent quality" in doc["markdown"]
    # Consolidated body is the approved department drafts only.
    ids = [s["department_id"] for s in doc["sections"]]
    assert ids == depts
    assert all(s.get("approval_status") == "approved" for s in doc["sections"])
    assert "Setup in 12 business days" in doc["markdown"]
    assert "USD $20" in doc["markdown"]
    assert "training" not in ids
    assert "Mariana Restrepo" not in doc["markdown"]
    synth = [e for e in result.trace if e.get("node") == "synthesizer"]
    assert synth
    assert synth[-1].get("output", {}).get("completion") == (
        "consolidated_approved_sections"
    )


def test_consolidate_approved_sections_excludes_non_approved() -> None:
    from data.pipelines.rfp_approval.synthesizer import (
        build_final_document,
        consolidate_approved_sections,
    )

    approvals = {
        "marketing": {
            "department_id": "marketing",
            "approval_status": "approved",
            "approver": "Camila Ospina",
        },
        "operaciones": {
            "department_id": "operaciones",
            "approval_status": "rejected",
            "approver": "Felipe Guerrero",
        },
        "procurement": {
            "department_id": "procurement",
            "approval_status": "pending",
        },
    }
    consolidated = consolidate_approved_sections(
        sections=SECTIONS,
        departments_needed=["marketing", "operaciones", "procurement"],
        approvals=approvals,
    )
    assert [s["department_id"] for s in consolidated] == ["marketing"]
    doc = build_final_document(
        ticket_id="partial",
        sections=SECTIONS,
        departments_needed=["marketing", "operaciones", "procurement"],
        approvals=approvals,
        metadata={"estimated_contract_value_usd": 20_000},
    )
    assert [s["department_id"] for s in doc["sections"]] == ["marketing"]
    assert "operaciones" not in [s["department_id"] for s in doc["sections"]]
    assert "## Restaurant Operations" not in doc["markdown"]
    assert "Brand terms" in doc["markdown"] or "30 days" in doc["markdown"]


def test_sunset_bay_blocks_until_ceo_mariana_approves() -> None:
    depts = ["marketing", "operaciones", "procurement"]
    sections = list(SECTIONS)
    base = dict(
        ticket_id="sunset-ceo",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=sections,
        metadata={
            "client_name": "Sunset Bay Resorts, LLC",
            "estimated_contract_value_usd": 75_000,
        },
        departments_needed=depts,
        requires_ceo_approval=True,
    )
    pending = run_approval_pipeline(**base, queued_decisions=_approve_all(depts))
    assert pending.status == STATUS_WAITING_FOR_APPROVAL
    assert pending.final_document in ({}, None) or not pending.final_document.get("markdown")
    assert pending.requires_ceo_approval is True
    assert any(p.get("department_id") == "ceo" for p in pending.pending_approvals)

    rejected = run_approval_pipeline(
        **base,
        approvals={
            d: {"department_id": d, "approval_status": "approved", "approver": DEPARTMENT_OWNERS[d]}
            for d in depts
        },
        queued_decisions=[
            {
                "department_id": "ceo",
                "decision": "rejected",
                "approver": "Mariana Restrepo",
            }
        ],
    )
    assert rejected.status != STATUS_DONE
    assert rejected.synthesizer_blocked is True
    assert not (rejected.final_document or {}).get("markdown")

    done = run_approval_pipeline(
        **base,
        approvals={
            d: {"department_id": d, "approval_status": "approved", "approver": DEPARTMENT_OWNERS[d]}
            for d in depts
        },
        queued_decisions=[
            {
                "department_id": "ceo",
                "decision": "approved",
                "approver": "Mariana Restrepo",
            }
        ],
    )
    assert done.status == STATUS_DONE
    assert done.final_document["total_estimated_value"] == 75_000
    assert "Mariana Restrepo" in done.final_document["markdown"]


def test_request_changes_blocks_final_document() -> None:
    depts = ["marketing", "operaciones", "procurement"]
    decisions = _approve_all(depts)
    decisions[1] = {
        "department_id": "operaciones",
        "decision": "request_changes",
        "approver": "Felipe Guerrero",
        "comment": "Raise the per-event price",
    }
    result = run_approval_pipeline(
        ticket_id="request-changes",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=SECTIONS,
        metadata={"estimated_contract_value_usd": 10_000},
        departments_needed=depts,
        queued_decisions=decisions,
    )
    assert result.status == STATUS_WAITING_FOR_APPROVAL
    assert result.approvals["operaciones"]["approval_status"] == "request_changes"
    assert not (result.final_document or {}).get("markdown")
