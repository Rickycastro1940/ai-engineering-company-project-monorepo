"""Evaluate/fix: no jumps, inconsistent messages, or data loss across parts.

Covers remaining gaps on top of ``test_rfp_part_transitions.py``:
- Part 1 key_aspects + metadata survive Part 2 draft upserts
- Part 2→3 handoff sets section approval_status=pending (not ticket status)
- Final-document 409 messages match actual ticket status
- Upload UI re-renders after start-approval (no stale Part 2 panel)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_approval.handoff import assert_part2_ready_for_approval
from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_response.part3_handoff import build_part3_handoff
from services.rfp import router as rfp_router
from services.rfp.models import RfpDepartmentSection
from services.rfp.store import (
    get_engine,
    init_db,
    list_sections,
    persist_part2_progress,
    reset_engine,
    save_response_result,
    ticket_to_dict,
)

ARTIFACT = Path("/opt/cursor/artifacts/rfp_part_transitions_fix.json")
REPO = Path(__file__).resolve().parents[2]
UI_UPLOAD = REPO / "uis" / "backoffice" / "rfp-upload.html"
ANDES_PDF = REPO / "rfp-requests" / "brasaland" / "CONTEXT-brasaland-request-2.pdf"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'part-fix.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "part-fix-ckpt.sqlite"))
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_upload_ui_rerenders_after_start_approval_no_stale_panel() -> None:
    src = UI_UPLOAD.read_text(encoding="utf-8")
    chunk = src[src.index("Starting approval graph") : src.index("deptSignoff.addEventListener")]
    assert "renderTicket(data)" in chunk, "start-approval must refresh the ticket panel"
    assert "pipeline complete" in src
    assert "Part 1 intake done" in src


def test_part3_handoff_sections_carry_pending_approval_status() -> None:
    handoff = build_part3_handoff(
        ticket_id="handoff-pending",
        ticket_status=STATUS_NEEDS_HUMAN_REVIEW,
        section_results=[
            {
                "department_id": "marketing",
                "owner": "Camila Ospina",
                "draft_content": "## Brand terms\nOffer validity period: 30 days.\n",
                "evaluation_results": {"passed": False},
                "passed": False,
                "exhausted": True,
                "section_status": STATUS_NEEDS_HUMAN_REVIEW,
            }
        ],
    )
    assert handoff["status"] == STATUS_NEEDS_HUMAN_REVIEW
    section = handoff["sections"][0]
    assert section["approval_status"] == "pending"
    assert section["status"] == STATUS_NEEDS_HUMAN_REVIEW
    assert section["draft_content"]
    assert section["evaluation_results"]

    ready = assert_part2_ready_for_approval(
        ticket_id="handoff-pending",
        status=STATUS_NEEDS_HUMAN_REVIEW,
        sections=handoff["sections"],
        part3_handoff=handoff,
    )
    assert ready["sections"][0]["approval_status"] == "pending"
    assert ready["status"] == STATUS_WAITING_FOR_APPROVAL


def test_key_aspects_and_metadata_survive_part2_upsert(client: TestClient) -> None:
    with ANDES_PDF.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (ANDES_PDF.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    assert created["status"] == STATUS_INTAKE_COMPLETE
    client_name = (created.get("metadata") or {}).get("client_name")
    assert client_name
    depts = list(created["departments_needed"])
    before = {s["department_id"]: s.get("key_aspects") for s in created["department_sections"]}
    assert any(before.values()), "Part 1 must seed key_aspects"

    dept = depts[0]
    assert persist_part2_progress(
        ticket_id,
        status="drafting",
        section_results=[
            {
                "department_id": dept,
                "draft_content": "## Draft v1\nOffer validity period: 30 days from issuance.\n",
                "passed": False,
                "evaluation_results": {"passed": False, "feedback": ["tweak"]},
            }
        ],
    )
    row = next(r for r in list_sections(ticket_id) if r.department_id == dept)
    assert row.draft_content and "Draft v1" in row.draft_content
    aspects = json.loads(row.key_aspects_json or "[]")
    assert aspects == before[dept], "Part 2 upsert must not wipe Part 1 key_aspects"
    assert json.loads(row.evaluation_results_json or "{}").get("feedback") == ["tweak"]

    detail = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert (detail.get("metadata") or {}).get("client_name") == client_name
    assert detail["status"] == "drafting"
    assert detail.get("part1_terminal") is False
    assert detail.get("pipeline_complete") is False


def test_full_transition_preserves_drafts_and_consistent_messages(
    client: TestClient,
) -> None:
    with ANDES_PDF.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (ANDES_PDF.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    depts = list(created["departments_needed"])
    client_name = (created.get("metadata") or {}).get("client_name")

    blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert blocked.status_code == 409
    assert STATUS_INTAKE_COMPLETE in blocked.json()["detail"]
    assert "until required owners" not in blocked.json()["detail"]

    generated = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["status"] in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}
    assert (body.get("metadata") or {}).get("client_name") == client_name
    sections = body["department_sections"]
    assert {s["department_id"] for s in sections} == set(depts)
    assert all(s.get("draft_content") for s in sections)
    assert all(s.get("key_aspects") for s in sections)
    assert all(s.get("approval_status") == "pending" for s in sections)

    started = client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    assert started.status_code == 200, started.text
    started_body = started.json()
    assert started_body["status"] == STATUS_WAITING_FOR_APPROVAL
    assert started_body.get("pipeline_complete") is False
    pending = (started_body.get("part3_pipeline") or {}).get("pending_approvals") or []
    assert {p["department_id"] for p in pending} == set(depts)

    mid = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert mid.status_code == 409
    assert STATUS_WAITING_FOR_APPROVAL in mid.json()["detail"]

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
    assert (final.get("metadata") or {}).get("client_name") == client_name
    assert final.get("final_document", {}).get("markdown")
    doc = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert doc.status_code == 200
    assert doc.json()["ticket_id"] == ticket_id

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "No jump, inconsistent message, or data loss in transitions "
                    "between parts"
                ),
                "verdict": "pass",
                "fixes": [
                    "rfp-upload.html start-approval calls renderTicket",
                    "part3_handoff sections include approval_status=pending",
                    "final-document 409 cites actual ticket status",
                    "ticket_to_dict always includes part1_terminal + pipeline_complete",
                ],
                "ticket_id": ticket_id,
                "client_name_preserved": client_name,
                "departments": depts,
                "statuses": {
                    "after_intake": STATUS_INTAKE_COMPLETE,
                    "after_part2": body["status"],
                    "after_start_approval": started_body["status"],
                    "after_all_approvals": final["status"],
                },
                "final_document_http": doc.status_code,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
