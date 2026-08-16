"""Evaluate: ticket status waiting_for_approval while HITL pending; done when FinalDocument accessible.

Proves in code (not docs alone):
1. Store/HTTP: FinalDocument requires ``done``; otherwise GET → 409
2. ``persist_part3_progress`` forces ``done`` when storing a FinalDocument
3. Runtime HTTP: during HITL (and after partial approvals) status is
   ``waiting_for_approval`` and final-document is blocked; after all owners
   approve, status is ``done`` and the document is accessible
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from data.pipelines.rfp_intake.constants import STATUS_DONE, STATUS_WAITING_FOR_APPROVAL
from services.api.database import get_engine
from services.rfp import router as rfp_router
from services.rfp.models import RfpDepartmentSection, RfpTicket
from services.rfp.routes import get_ticket_final_document
from services.rfp.store import (
    create_analyzing_ticket,
    get_final_document,
    init_db,
    persist_part3_progress,
    reset_engine,
)

ARTIFACT = Path("/opt/cursor/artifacts/rfp_ticket_status_hitl_done.json")
REPO = Path(__file__).resolve().parents[2]

ANDES_DRAFTS = {
    "marketing": "## Brand terms\nOffer validity period: 30 days from issuance.\n",
    "operaciones": "## Setup times\nSetup in 12 business days.\n## Cost per event\nUSD $40.\n",
    "procurement": "## Estimated ingredient cost based on volume\nUSD $20.\n",
}
OWNERS = {
    "marketing": "Camila Ospina",
    "operaciones": "Felipe Guerrero",
    "procurement": "Lucía Fernández",
}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'status-hitl.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv(
        "RFP_CHECKPOINT_SQLITE", str(tmp_path / "status-hitl-checkpoints.sqlite")
    )
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def _seed_andes() -> str:
    ticket = create_analyzing_ticket(title="status-hitl")
    depts = list(ANDES_DRAFTS)
    with Session(get_engine()) as session:
        row = session.get(RfpTicket, ticket.ticket_id)
        assert row is not None
        row.status = STATUS_WAITING_FOR_APPROVAL
        row.part3_ready = True
        row.requires_ceo_approval = False
        row.departments_needed_json = json.dumps(depts)
        row.metadata_json = json.dumps(
            {
                "client_name": "Andes Tech Solutions",
                "estimated_contract_value_usd": 20_000,
            }
        )
        session.add(row)
        for dept in depts:
            session.add(
                RfpDepartmentSection(
                    ticket_id=ticket.ticket_id,
                    department_id=dept,
                    key_aspects_json=json.dumps([f"{dept} aspects"]),
                    draft_content=ANDES_DRAFTS[dept],
                    approval_status="pending",
                )
            )
        session.commit()
    return ticket.ticket_id


def test_store_and_http_source_tie_final_doc_to_done_status() -> None:
    store_src = (
        REPO / "services" / "rfp" / "store.py"
    ).read_text(encoding="utf-8")
    route_src = inspect.getsource(get_ticket_final_document)
    persist_src = inspect.getsource(persist_part3_progress)

    assert "require_done" in store_src
    assert "STATUS_DONE" in persist_src
    assert "if final_document:" in persist_src
    assert "status = STATUS_DONE" in persist_src
    assert "ticket.status != STATUS_DONE" in route_src
    assert "409" in route_src or "status_code=409" in route_src


def test_http_waiting_while_hitl_pending_done_when_final_doc_accessible(
    client: TestClient,
) -> None:
    ticket_id = _seed_andes()
    depts = list(ANDES_DRAFTS)
    snapshots: list[dict] = []

    started = client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == STATUS_WAITING_FOR_APPROVAL

    detail = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert detail["status"] == STATUS_WAITING_FOR_APPROVAL
    blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert blocked.status_code == 409
    assert STATUS_DONE in blocked.json()["detail"]
    assert get_final_document(ticket_id, require_done=True) is None
    snapshots.append(
        {
            "phase": "hitl_started_all_pending",
            "status": detail["status"],
            "final_document_http": blocked.status_code,
            "require_done_store": None,
        }
    )

    # Partial approvals: still waiting; FinalDocument still blocked.
    for i, dept in enumerate(depts[:-1]):
        res = client.post(
            f"/rfp/tickets/{ticket_id}/approvals",
            json={
                "department_id": dept,
                "decision": "approved",
                "approver": OWNERS[dept],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == STATUS_WAITING_FOR_APPROVAL
        detail = client.get(f"/rfp/tickets/{ticket_id}").json()
        assert detail["status"] == STATUS_WAITING_FOR_APPROVAL
        blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
        assert blocked.status_code == 409
        assert get_final_document(ticket_id, require_done=True) is None
        snapshots.append(
            {
                "phase": f"after_approve_{dept}",
                "approved_so_far": depts[: i + 1],
                "status": detail["status"],
                "final_document_http": blocked.status_code,
            }
        )

    # Last owner → done + FinalDocument accessible.
    last_dept = depts[-1]
    last = client.post(
        f"/rfp/tickets/{ticket_id}/approvals",
        json={
            "department_id": last_dept,
            "decision": "approved",
            "approver": OWNERS[last_dept],
        },
    )
    assert last.status_code == 200, last.text
    assert last.json()["status"] == STATUS_DONE

    detail = client.get(f"/rfp/tickets/{ticket_id}").json()
    assert detail["status"] == STATUS_DONE
    assert detail.get("pipeline_complete") is True
    doc_res = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert doc_res.status_code == 200, doc_res.text
    doc = doc_res.json()
    assert doc["ticket_id"] == ticket_id
    assert doc.get("generated_at")
    assert doc.get("sections")
    stored = get_final_document(ticket_id, require_done=True)
    assert stored is not None
    assert stored["ticket_id"] == ticket_id
    assert detail.get("final_document", {}).get("markdown")

    snapshots.append(
        {
            "phase": f"after_approve_{last_dept}_complete",
            "approved_so_far": depts,
            "status": detail["status"],
            "final_document_http": doc_res.status_code,
            "final_ticket_id": doc["ticket_id"],
            "pipeline_complete": detail.get("pipeline_complete"),
        }
    )

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "Ticket status uses waiting_for_approval while HITL is pending "
                    "and done when the final document is accessible"
                ),
                "verdict": "pass",
                "rules": {
                    "hitl_pending": STATUS_WAITING_FOR_APPROVAL,
                    "final_document_accessible": STATUS_DONE,
                    "blocked_http": 409,
                },
                "ticket_id": ticket_id,
                "snapshots": snapshots,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
