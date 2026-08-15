"""End-to-end review: one CONTEXT seed RFP through intake → generation → approval → completion.

Confirms ticket_id, status transitions, messages, and data stay consistent on the
same ticket from upload through FinalDocument.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_approval.approvers import CEO_NAME, DEPARTMENT_OWNERS
from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_DRAFTING,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_UNDER_EVALUATION,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS
from services.rfp import router as rfp_router
from services.rfp.store import (
    get_final_document,
    get_ticket,
    init_db,
    list_sections,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
ANDES_PDF = SEEDS / "CONTEXT-brasaland-request-2.pdf"
SUNSET_PDF = SEEDS / "CONTEXT-brasaland-request-1.pdf"
ARTIFACT = Path("/opt/cursor/artifacts/rfp_e2e_andes_journey.json")


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'e2e.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "e2e-checkpoints.sqlite"))
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def _journey_step(name: str, payload: dict) -> dict:
    return {
        "step": name,
        "ticket_id": payload.get("ticket_id"),
        "status": payload.get("status"),
        "departments_needed": list(payload.get("departments_needed") or []),
        "requires_ceo_approval": bool(payload.get("requires_ceo_approval")),
        "client_name": (payload.get("metadata") or {}).get("client_name"),
        "part2_ready": payload.get("part2_ready"),
        "part3_ready": payload.get("part3_ready"),
        "section_statuses": {
            s["department_id"]: s.get("approval_status")
            for s in (payload.get("department_sections") or [])
        },
    }


def test_e2e_andes_intake_generation_approval_completion(client: TestClient) -> None:
    """Informal Andes RFP: all four parts on one ticket, no CEO."""
    assert ANDES_PDF.is_file()
    expected = CONTEXT_SEED_EXPECTATIONS[ANDES_PDF.name]
    journey: list[dict] = []

    # --- Part 1: intake ---
    with ANDES_PDF.open("rb") as fh:
        intake = client.post(
            "/rfp/tickets",
            files={"file": (ANDES_PDF.name, fh, "application/pdf")},
            data={"title": "E2E Andes Tech RFP"},
        )
    assert intake.status_code == 200, intake.text
    body = intake.json()
    ticket_id = body["ticket_id"]
    assert body["status"] == STATUS_INTAKE_COMPLETE
    assert body["part2_ready"] is True
    assert expected["client_substr"] in (body.get("metadata") or {}).get("client_name", "")
    assert set(body["departments_needed"]) == set(expected["departments"])
    assert body["requires_ceo_approval"] is False
    assert "training" not in body["departments_needed"]
    assert body.get("intake_summary")
    journey.append(_journey_step("intake", body))

    # --- Part 2: generation ---
    generated = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["ticket_id"] == ticket_id
    assert body["status"] in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}
    assert body.get("part3_ready") is True
    history = body.get("part2_status_history") or []
    assert history[0] == STATUS_INTAKE_COMPLETE
    assert STATUS_DRAFTING in history
    assert STATUS_UNDER_EVALUATION in history
    assert history[-1] == body["status"]
    sections = body.get("department_sections") or []
    assert {s["department_id"] for s in sections} == set(expected["departments"])
    for row in sections:
        assert row.get("draft_content"), row
        assert row.get("evaluation_results"), row
        assert row.get("approval_status") in {None, "pending", STATUS_NEEDS_HUMAN_REVIEW}
    # Same ticket metadata / departments after generation
    assert expected["client_substr"] in (body.get("metadata") or {}).get("client_name", "")
    assert set(body["departments_needed"]) == set(expected["departments"])
    journey.append(_journey_step("generation", body))

    # Final document must stay inaccessible while approvals are pending.
    blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert blocked.status_code == 409

    # --- Part 3: approval start ---
    started = client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["ticket_id"] == ticket_id
    assert body["status"] == STATUS_WAITING_FOR_APPROVAL
    assert all(
        (s.get("approval_status") or "pending") == "pending"
        for s in body.get("department_sections") or []
    )
    journey.append(_journey_step("start_approval", body))

    # --- Part 3: named-owner approvals (any order) ---
    last = body
    for dept in ("operaciones", "marketing", "procurement"):
        res = client.post(
            f"/rfp/tickets/{ticket_id}/approvals",
            json={
                "department_id": dept,
                "decision": "approved",
                "approver": DEPARTMENT_OWNERS[dept],
            },
        )
        assert res.status_code == 200, res.text
        last = res.json()
        assert last["ticket_id"] == ticket_id
        by_dept = {
            s["department_id"]: s.get("approval_status")
            for s in last.get("department_sections") or []
        }
        assert by_dept[dept] == "approved"
        journey.append(_journey_step(f"approve_{dept}", last))

    # --- Completion ---
    assert last["status"] == STATUS_DONE
    doc_res = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert doc_res.status_code == 200, doc_res.text
    doc = doc_res.json()
    assert doc["ticket_id"] == ticket_id
    assert doc.get("generated_at")
    assert doc.get("sections")
    assert {s["department_id"] for s in doc["sections"]} == set(expected["departments"])
    assert all(s.get("approval_status") == "approved" for s in doc["sections"])
    assert expected["client_substr"] in (doc.get("markdown") or "")
    assert "Mariana Restrepo" not in (doc.get("markdown") or "")

    detail = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert detail["ticket_id"] == ticket_id
    assert detail["status"] == STATUS_DONE
    assert detail.get("final_document", {}).get("markdown")
    assert set(detail["departments_needed"]) == set(expected["departments"])
    assert expected["client_substr"] in (detail.get("metadata") or {}).get(
        "client_name", ""
    )

    stored = get_final_document(ticket_id, require_done=True)
    assert stored is not None
    assert stored["ticket_id"] == ticket_id
    rows = list_sections(ticket_id)
    assert {r.department_id: r.approval_status for r in rows} == {
        d: "approved" for d in expected["departments"]
    }
    assert all(r.approver == DEPARTMENT_OWNERS[r.department_id] for r in rows)
    assert all(r.approved_at for r in rows)

    # Journey consistency: one ticket_id from start to finish
    assert {step["ticket_id"] for step in journey} == {ticket_id}
    assert journey[0]["status"] == STATUS_INTAKE_COMPLETE
    assert journey[-1]["status"] == STATUS_DONE
    assert all(
        set(step["departments_needed"]) == set(expected["departments"]) for step in journey
    )

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "seed": ANDES_PDF.name,
                "ticket_id": ticket_id,
                "journey": journey,
                "final_document": {
                    "ticket_id": doc["ticket_id"],
                    "generated_at": doc.get("generated_at"),
                    "total_estimated_value": doc.get("total_estimated_value"),
                    "section_ids": [s["department_id"] for s in doc["sections"]],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_e2e_sunset_requires_ceo_before_completion(client: TestClient) -> None:
    """Formal Sunset Bay RFP: CEO Mariana must approve before done."""
    assert SUNSET_PDF.is_file()
    expected = CONTEXT_SEED_EXPECTATIONS[SUNSET_PDF.name]

    with SUNSET_PDF.open("rb") as fh:
        intake = client.post(
            "/rfp/tickets",
            files={"file": (SUNSET_PDF.name, fh, "application/pdf")},
            data={"title": "E2E Sunset Bay RFP"},
        )
    assert intake.status_code == 200, intake.text
    body = intake.json()
    ticket_id = body["ticket_id"]
    assert body["status"] == STATUS_INTAKE_COMPLETE
    assert body["requires_ceo_approval"] is True
    assert set(body["departments_needed"]) == set(expected["departments"])
    assert expected["client_substr"] in (body.get("metadata") or {}).get("client_name", "")

    generated = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert generated.status_code == 200, generated.text
    assert generated.json()["ticket_id"] == ticket_id
    assert generated.json().get("part3_ready") is True

    started = client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == STATUS_WAITING_FOR_APPROVAL

    for dept in sorted(expected["departments"]):
        res = client.post(
            f"/rfp/tickets/{ticket_id}/approvals",
            json={
                "department_id": dept,
                "decision": "approved",
                "approver": DEPARTMENT_OWNERS[dept],
            },
        )
        assert res.status_code == 200, res.text

    # Departments approved but CEO still required → not done / no document yet
    mid = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert mid["ticket_id"] == ticket_id
    assert mid["status"] == STATUS_WAITING_FOR_APPROVAL
    assert client.get(f"/rfp/tickets/{ticket_id}/final-document").status_code == 409

    ceo = client.post(
        f"/rfp/tickets/{ticket_id}/approvals",
        json={
            "department_id": "ceo",
            "decision": "approved",
            "approver": CEO_NAME,
        },
    )
    assert ceo.status_code == 200, ceo.text
    assert ceo.json()["status"] == STATUS_DONE
    assert ceo.json()["ticket_id"] == ticket_id

    doc = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert doc.status_code == 200, doc.text
    assert doc.json()["ticket_id"] == ticket_id
    assert CEO_NAME in (doc.json().get("markdown") or "")
    assert expected["client_substr"] in (doc.json().get("markdown") or "")

    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status == STATUS_DONE
    assert ticket_to_dict(ticket)["final_document"].get("markdown")
