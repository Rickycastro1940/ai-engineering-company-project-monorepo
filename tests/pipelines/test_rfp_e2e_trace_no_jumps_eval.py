"""Evaluate: test RFP traced Part 1→3 with no state jumps or visible inconsistency.

Uses the CONTEXT Andes seed end-to-end over HTTP and asserts:
- one stable ``ticket_id`` / client / departments across every step
- ticket status only moves along an allowed transition graph (no jumps)
- ``part1_terminal`` / ``pipeline_complete`` stay consistent with status
- FinalDocument is blocked until ``done``, then accessible
- section ``approval_status`` never shows ticket-level ``needs_human_review``
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_DRAFTING,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_UNDER_EVALUATION,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS

ARTIFACT = Path("/opt/cursor/artifacts/rfp_e2e_trace_no_jumps.json")
REPO = Path(__file__).resolve().parents[2]
ANDES_PDF = REPO / "rfp-requests" / "brasaland" / "CONTEXT-brasaland-request-2.pdf"

# Allowed ticket-status edges for a happy-path Andes run (no CEO).
# Part 2 may land on waiting_for_approval or needs_human_review; both enter Part 3.
ALLOWED_EDGES: set[tuple[str, str]] = {
    (STATUS_INTAKE_COMPLETE, STATUS_WAITING_FOR_APPROVAL),
    (STATUS_INTAKE_COMPLETE, STATUS_NEEDS_HUMAN_REVIEW),
    (STATUS_INTAKE_COMPLETE, STATUS_DRAFTING),  # if history sampled mid-Part-2
    (STATUS_DRAFTING, STATUS_UNDER_EVALUATION),
    (STATUS_UNDER_EVALUATION, STATUS_WAITING_FOR_APPROVAL),
    (STATUS_UNDER_EVALUATION, STATUS_NEEDS_HUMAN_REVIEW),
    (STATUS_NEEDS_HUMAN_REVIEW, STATUS_WAITING_FOR_APPROVAL),
    (STATUS_WAITING_FOR_APPROVAL, STATUS_WAITING_FOR_APPROVAL),  # partial approvals
    (STATUS_WAITING_FOR_APPROVAL, STATUS_DONE),
}


def _assert_no_status_jumps(statuses: list[str]) -> None:
    compact = [statuses[0]]
    for status in statuses[1:]:
        if status != compact[-1]:
            compact.append(status)
    for left, right in zip(compact, compact[1:]):
        assert (left, right) in ALLOWED_EDGES, (
            f"illegal status jump {left!r} → {right!r}; path={compact}"
        )


def _snapshot(step: str, payload: dict) -> dict:
    return {
        "step": step,
        "ticket_id": payload.get("ticket_id"),
        "status": payload.get("status"),
        "client_name": (payload.get("metadata") or {}).get("client_name"),
        "departments_needed": list(payload.get("departments_needed") or []),
        "requires_ceo_approval": bool(payload.get("requires_ceo_approval")),
        "part1_terminal": payload.get("part1_terminal"),
        "pipeline_complete": payload.get("pipeline_complete"),
        "part2_ready": payload.get("part2_ready"),
        "part3_ready": payload.get("part3_ready"),
        "section_approval_statuses": {
            s["department_id"]: s.get("approval_status")
            for s in (payload.get("department_sections") or [])
        },
        "has_drafts": all(
            bool(s.get("draft_content"))
            for s in (payload.get("department_sections") or [])
        )
        if payload.get("department_sections")
        else None,
        "has_key_aspects": all(
            bool(s.get("key_aspects"))
            for s in (payload.get("department_sections") or [])
        )
        if payload.get("department_sections")
        else None,
        "final_document_present": bool(
            (payload.get("final_document") or {}).get("markdown")
            or (payload.get("final_document") or {}).get("ticket_id")
        ),
    }


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from services.rfp import router as rfp_router
    from services.rfp.store import init_db, reset_engine

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'e2e-trace.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "e2e-trace-ckpt.sqlite"))
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_andes_rfp_traced_part1_through_part3_without_jumps_or_inconsistency(
    client: TestClient,
) -> None:
    assert ANDES_PDF.is_file()
    expected = CONTEXT_SEED_EXPECTATIONS[ANDES_PDF.name]
    journey: list[dict] = []
    final_doc_http: list[dict] = []

    # --- Part 1 ---
    with ANDES_PDF.open("rb") as fh:
        intake = client.post(
            "/rfp/tickets",
            files={"file": (ANDES_PDF.name, fh, "application/pdf")},
            data={"title": "E2E trace Andes"},
        )
    assert intake.status_code == 200, intake.text
    body = intake.json()
    ticket_id = body["ticket_id"]
    client_name = (body.get("metadata") or {}).get("client_name") or ""
    depts = list(body["departments_needed"])
    assert body["status"] == STATUS_INTAKE_COMPLETE
    assert body.get("part1_terminal") is True
    assert body.get("pipeline_complete") is False
    assert body.get("part2_ready") is True
    assert body.get("part3_ready") in {False, None}
    assert expected["client_substr"] in client_name
    assert set(depts) == set(expected["departments"])
    assert body["requires_ceo_approval"] is False
    journey.append(_snapshot("part1_intake", body))

    blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert blocked.status_code == 409
    assert STATUS_INTAKE_COMPLETE in blocked.json()["detail"]
    final_doc_http.append({"after": "part1", "http": 409, "detail": blocked.json()["detail"]})

    # --- Part 2 ---
    generated = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["ticket_id"] == ticket_id
    assert (body.get("metadata") or {}).get("client_name") == client_name
    assert set(body["departments_needed"]) == set(depts)
    assert body["status"] in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}
    assert body.get("part3_ready") is True
    assert body.get("pipeline_complete") is False
    assert body.get("part1_terminal") is False
    history = body.get("part2_status_history") or []
    assert history[0] == STATUS_INTAKE_COMPLETE
    assert STATUS_DRAFTING in history
    assert STATUS_UNDER_EVALUATION in history
    assert history[-1] == body["status"]
    _assert_no_status_jumps(history)
    for row in body.get("department_sections") or []:
        assert row.get("draft_content"), row
        assert row.get("key_aspects"), row
        assert row.get("evaluation_results"), row
        assert row.get("approval_status") == "pending"
        assert row.get("approval_status") != STATUS_NEEDS_HUMAN_REVIEW
    journey.append(_snapshot("part2_generation", body))

    blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert blocked.status_code == 409
    assert body["status"] in blocked.json()["detail"]
    final_doc_http.append({"after": "part2", "http": 409})

    # --- Part 3 start ---
    started = client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["ticket_id"] == ticket_id
    assert body["status"] == STATUS_WAITING_FOR_APPROVAL
    assert body.get("pipeline_complete") is False
    assert (body.get("metadata") or {}).get("client_name") == client_name
    assert set(body["departments_needed"]) == set(depts)
    pending = (body.get("part3_pipeline") or {}).get("pending_approvals") or []
    assert {p["department_id"] for p in pending} == set(depts)
    journey.append(_snapshot("part3_start_approval", body))

    # --- Part 3 approvals (order differs from intake order — still no jump) ---
    last = body
    for dept in ("procurement", "marketing", "operaciones"):
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
        assert (last.get("metadata") or {}).get("client_name") == client_name
        assert set(last["departments_needed"]) == set(depts)
        by_dept = {
            s["department_id"]: s.get("approval_status")
            for s in last.get("department_sections") or []
        }
        assert by_dept[dept] == "approved"
        # Never surface ticket needs_human_review on section rows mid-HITL.
        assert STATUS_NEEDS_HUMAN_REVIEW not in by_dept.values()
        if dept != "operaciones":
            assert last["status"] == STATUS_WAITING_FOR_APPROVAL
            assert last.get("pipeline_complete") is False
            assert not (last.get("final_document") or {}).get("markdown")
            blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
            assert blocked.status_code == 409
        journey.append(_snapshot(f"part3_approve_{dept}", last))

    assert last["status"] == STATUS_DONE
    assert last.get("pipeline_complete") is True
    assert last.get("part1_terminal") is False
    doc = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert doc.status_code == 200, doc.text
    payload = doc.json()
    assert payload["ticket_id"] == ticket_id
    assert expected["client_substr"] in (payload.get("markdown") or "")
    assert {s["department_id"] for s in payload["sections"]} == set(depts)
    final_doc_http.append({"after": "part3_complete", "http": 200})

    detail = client.get(f"/rfp/tickets/{ticket_id}").json()
    journey.append(_snapshot("part3_done_get", detail))
    assert detail["status"] == STATUS_DONE
    assert detail.get("pipeline_complete") is True
    assert detail.get("final_document", {}).get("markdown")

    # --- Global consistency ---
    assert {s["ticket_id"] for s in journey} == {ticket_id}
    assert all(s["client_name"] == client_name for s in journey)
    assert all(set(s["departments_needed"]) == set(depts) for s in journey)
    assert all(s["requires_ceo_approval"] is False for s in journey)
    _assert_no_status_jumps([s["status"] for s in journey])

    # Visible flag consistency with status
    for step in journey:
        status = step["status"]
        if status == STATUS_INTAKE_COMPLETE:
            assert step["part1_terminal"] is True
            assert step["pipeline_complete"] is False
            assert step["final_document_present"] is False
        elif status == STATUS_DONE:
            assert step["pipeline_complete"] is True
            assert step["part1_terminal"] is False
        else:
            assert step["pipeline_complete"] is False
            assert step["part1_terminal"] is False
            assert step["final_document_present"] is False

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "A test RFP can be traced end to end (Part 1 through Part 3) "
                    "with no state jumps or visible inconsistency between parts"
                ),
                "verdict": "pass",
                "seed": ANDES_PDF.name,
                "ticket_id": ticket_id,
                "client_name": client_name,
                "status_path": [s["status"] for s in journey],
                "part2_status_history": history,
                "final_document_http": final_doc_http,
                "journey": journey,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
