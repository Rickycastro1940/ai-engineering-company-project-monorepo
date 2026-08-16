"""Regression: no jumps, inconsistent messages, or data loss across Parts 1→2→3→4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_approval.handoff import normalize_section_approval_status
from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_DRAFTING,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_UNDER_EVALUATION,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_response import Part1HandoffNotReady, assert_part1_routing_ready
from services.rfp import router as rfp_router
from services.rfp.models import RfpDepartmentSection
from services.rfp.store import (
    get_engine,
    get_ticket,
    init_db,
    list_sections,
    persist_part2_progress,
    reset_engine,
    save_response_result,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
ANDES_PDF = SEEDS / "CONTEXT-brasaland-request-2.pdf"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'transitions.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "transitions-ckpt.sqlite"))
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_normalize_section_approval_status_drops_ticket_status_leak() -> None:
    assert normalize_section_approval_status("needs_human_review") == "pending"
    assert normalize_section_approval_status("drafting") == "pending"
    assert normalize_section_approval_status("approved") == "approved"
    assert normalize_section_approval_status("request_changes") == "request_changes"


def test_assert_part1_allows_mid_part2_resume_statuses() -> None:
    handoff = {
        "ticket_id": "t-resume",
        "status": STATUS_INTAKE_COMPLETE,
        "part2_ready": True,
        "reparse_pdf_required": False,
        "work_streams": [
            {"department_id": "marketing", "key_aspects": ["Brand terms"]}
        ],
    }
    for status in (STATUS_DRAFTING, STATUS_UNDER_EVALUATION, STATUS_INTAKE_COMPLETE):
        assert_part1_routing_ready(
            ticket_id="t-resume",
            status=status,
            part2_ready=True,
            handoff=handoff,
        )
    with pytest.raises(Part1HandoffNotReady, match="intake_complete"):
        assert_part1_routing_ready(
            ticket_id="t-resume",
            status="analyzing",
            part2_ready=True,
            handoff=handoff,
        )
    with pytest.raises(Part1HandoffNotReady, match="drafting"):
        assert_part1_routing_ready(
            ticket_id="t-resume",
            status=STATUS_WAITING_FOR_APPROVAL,
            part2_ready=True,
            handoff=handoff,
        )


def test_exhausted_section_persists_pending_for_part3_hitl(client: TestClient) -> None:
    """Part 2 exhaustion must not write ticket status onto section.approval_status."""
    with ANDES_PDF.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (ANDES_PDF.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    depts = list(created["departments_needed"])
    assert depts

    class _Result:
        status = STATUS_NEEDS_HUMAN_REVIEW
        all_passed = False
        average_iterations = 2.0
        trace = []
        part3_handoff = {
            "ticket_id": ticket_id,
            "status": STATUS_NEEDS_HUMAN_REVIEW,
            "sections": [],
            "discarded": False,
            "next_part": 3,
        }
        section_results = [
            {
                "department_id": dept,
                "owner": DEPARTMENT_OWNERS[dept],
                "draft_content": f"## Exhausted draft for {dept}\nSetup in 12 business days.",
                "evaluation_results": {"passed": False, "feedback": ["x"]},
                "passed": False,
                "exhausted": True,
                "section_status": STATUS_NEEDS_HUMAN_REVIEW,
                "include_in_part3": True,
            }
            for dept in depts
        ]

    saved = save_response_result(ticket_id, _Result())
    assert saved.status == STATUS_NEEDS_HUMAN_REVIEW
    rows = list_sections(ticket_id)
    assert {r.department_id: r.approval_status for r in rows} == {
        d: "pending" for d in depts
    }
    public = ticket_to_dict(saved)
    assert all(
        s.get("approval_status") == "pending" for s in public["department_sections"]
    )

    # Legacy row with leaked ticket status still becomes pending at Part 3 entry.
    with Session(get_engine()) as session:
        row = session.exec(
            select(RfpDepartmentSection).where(
                RfpDepartmentSection.ticket_id == ticket_id,
                RfpDepartmentSection.department_id == depts[0],
            )
        ).first()
        assert row is not None
        row.approval_status = STATUS_NEEDS_HUMAN_REVIEW
        session.add(row)
        session.commit()

    started = client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == STATUS_WAITING_FOR_APPROVAL
    assert all(
        s.get("approval_status") == "pending"
        for s in body.get("department_sections") or []
    )
    pending = (body.get("part3_pipeline") or {}).get("pending_approvals") or []
    assert {p["department_id"] for p in pending} == set(depts)

    # Named-owner can still approve — no stranded waiting_for_approval.
    for dept in depts:
        res = client.post(
            f"/rfp/tickets/{ticket_id}/approvals",
            json={
                "department_id": dept,
                "decision": "approved",
                "approver": DEPARTMENT_OWNERS[dept],
            },
        )
        assert res.status_code == 200, res.text
    final = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert final["status"] == STATUS_DONE
    assert final.get("pipeline_complete") is True
    assert final.get("part1_terminal") is False


def test_generate_response_resumes_from_drafting(client: TestClient) -> None:
    with ANDES_PDF.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (ANDES_PDF.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    assert created["status"] == STATUS_INTAKE_COMPLETE
    assert persist_part2_progress(ticket_id, status=STATUS_DRAFTING) is True
    assert get_ticket(ticket_id).status == STATUS_DRAFTING  # type: ignore[union-attr]

    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ticket_id"] == ticket_id
    assert body["status"] in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}
    assert set(body["departments_needed"]) == set(created["departments_needed"])
    assert (body.get("metadata") or {}).get("client_name") == (
        created.get("metadata") or {}
    ).get("client_name")


def test_final_document_409_reports_actual_status(client: TestClient) -> None:
    with ANDES_PDF.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (ANDES_PDF.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert STATUS_INTAKE_COMPLETE in detail
    assert STATUS_DONE in detail
    assert "approvals are pending" not in detail

    got = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert got["terminal"] is True  # Part 1 intake finished
    assert got["part1_terminal"] is True
    assert got["pipeline_complete"] is False


def test_upsert_preserves_empty_draft_content_string(client: TestClient) -> None:
    with ANDES_PDF.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (ANDES_PDF.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    dept = created["departments_needed"][0]
    assert persist_part2_progress(
        ticket_id,
        status=STATUS_DRAFTING,
        section_results=[
            {
                "department_id": dept,
                "draft_content": "first",
                "passed": True,
                "evaluation_results": {"passed": True},
            }
        ],
    )
    assert persist_part2_progress(
        ticket_id,
        status=STATUS_UNDER_EVALUATION,
        section_results=[
            {
                "department_id": dept,
                "draft_content": "",
                "passed": False,
                "exhausted": True,
                "section_status": STATUS_NEEDS_HUMAN_REVIEW,
                "evaluation_results": {"passed": False},
            }
        ],
    )
    row = next(r for r in list_sections(ticket_id) if r.department_id == dept)
    assert row.draft_content == ""
    assert row.approval_status == "pending"
