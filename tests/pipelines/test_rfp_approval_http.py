"""Part 3 HTTP: same services/rfp API persists approvals + FinalDocument."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_WAITING_FOR_APPROVAL,
)
from services.api.database import get_engine
from services.rfp import router as rfp_router
from services.rfp.models import RfpDepartmentSection, RfpFinalDocument, RfpTicket
from services.rfp.store import (
    create_analyzing_ticket,
    get_final_document,
    init_db,
    list_sections,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
UI_PAGE = REPO / "uis" / "backoffice" / "rfp-approvals.html"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'part3.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "part3-checkpoints.sqlite"))
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def _seed_ticket(
    *,
    departments: list[str],
    requires_ceo: bool,
    metadata: dict,
    drafts: dict[str, str],
) -> str:
    ticket = create_analyzing_ticket(title="part3")
    with Session(get_engine()) as session:
        row = session.get(RfpTicket, ticket.ticket_id)
        assert row is not None
        row.status = STATUS_WAITING_FOR_APPROVAL
        row.part3_ready = True
        row.requires_ceo_approval = requires_ceo
        row.departments_needed_json = json.dumps(departments)
        row.metadata_json = json.dumps(metadata)
        session.add(row)
        for dept in departments:
            session.add(
                RfpDepartmentSection(
                    ticket_id=ticket.ticket_id,
                    department_id=dept,
                    key_aspects_json=json.dumps([f"{dept} aspects"]),
                    draft_content=drafts[dept],
                    approval_status="pending",
                )
            )
        session.commit()
    return ticket.ticket_id


ANDES_DRAFTS = {
    "marketing": "## Brand terms\nOffer validity period: 30 days from issuance.\n",
    "operaciones": "## Setup times\nSetup in 12 business days.\n## Cost per event\nUSD $40.\n",
    "procurement": "## Estimated ingredient cost based on volume\nUSD $20.\n",
}


def test_http_named_owners_approve_andes_without_ceo(client: TestClient) -> None:
    depts = ["marketing", "operaciones", "procurement"]
    ticket_id = _seed_ticket(
        departments=depts,
        requires_ceo=False,
        metadata={
            "client_name": "Andes Tech Solutions",
            "location": "Medellín",
            "estimated_contract_value_usd": 20_000,
        },
        drafts=ANDES_DRAFTS,
    )
    started = client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == STATUS_WAITING_FOR_APPROVAL
    assert all(r.approval_status == "pending" for r in list_sections(ticket_id))

    owners = {
        "operaciones": "Felipe Guerrero",
        "marketing": "Camila Ospina",
        "procurement": "Lucía Fernández",
    }
    last = None
    first = client.post(
        f"/rfp/tickets/{ticket_id}/approvals",
        json={
            "department_id": "operaciones",
            "decision": "approved",
            "approver": "Felipe Guerrero",
        },
    )
    assert first.status_code == 200, first.text
    by_dept = {r.department_id: r.approval_status for r in list_sections(ticket_id)}
    assert by_dept["operaciones"] == "approved"
    assert by_dept["marketing"] == "pending"
    assert by_dept["procurement"] == "pending"
    for dept, owner in owners.items():
        if dept == "operaciones":
            continue
        res = client.post(
            f"/rfp/tickets/{ticket_id}/approvals",
            json={
                "department_id": dept,
                "decision": "approved",
                "approver": owner,
            },
        )
        assert res.status_code == 200, res.text
        last = res.json()
    assert last is not None
    assert last["status"] == STATUS_DONE
    doc = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert doc.status_code == 200, doc.text
    payload = doc.json()
    assert payload["ticket_id"] == ticket_id
    assert payload["total_estimated_value"] == 20_000
    assert payload.get("generated_at")
    stored = get_final_document(ticket_id)
    assert stored is not None
    assert stored["markdown"]
    rows = list_sections(ticket_id)
    assert {r.department_id: r.approval_status for r in rows} == {
        dept: "approved" for dept in depts
    }
    assert all(r.approver for r in rows)
    assert all(r.approved_at for r in rows)


def test_http_rejects_invented_approver_title(client: TestClient) -> None:
    ticket_id = _seed_ticket(
        departments=["marketing"],
        requires_ceo=False,
        metadata={"client_name": "Andes Tech Solutions"},
        drafts={"marketing": ANDES_DRAFTS["marketing"]},
    )
    client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    res = client.post(
        f"/rfp/tickets/{ticket_id}/approvals",
        json={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "VP of Sales",
        },
    )
    assert res.status_code == 403
    detail = ticket_to_dict(
        __import__("services.rfp.store", fromlist=["get_ticket"]).get_ticket(ticket_id)
    )
    assert detail["status"] != STATUS_DONE


def test_http_invalid_decision_does_not_enter_graph(client: TestClient) -> None:
    ticket_id = _seed_ticket(
        departments=["marketing"],
        requires_ceo=False,
        metadata={"client_name": "Andes Tech Solutions"},
        drafts={"marketing": ANDES_DRAFTS["marketing"]},
    )
    client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    res = client.post(
        f"/rfp/tickets/{ticket_id}/approvals",
        json={
            "department_id": "marketing",
            "decision": "maybe",
            "approver": "Camila Ospina",
        },
    )
    assert res.status_code == 409, res.text
    assert "approve" in res.text.casefold() or "request_changes" in res.text.casefold()
    rows = {r.department_id: r.approval_status for r in list_sections(ticket_id)}
    assert rows["marketing"] == "pending"


def test_http_approval_without_start_does_not_restart_graph(client: TestClient) -> None:
    ticket_id = _seed_ticket(
        departments=["marketing"],
        requires_ceo=False,
        metadata={"client_name": "Andes Tech Solutions"},
        drafts={"marketing": ANDES_DRAFTS["marketing"]},
    )
    res = client.post(
        f"/rfp/tickets/{ticket_id}/approvals",
        json={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    assert res.status_code == 409, res.text
    assert "approval_not_paused" in res.text
    detail = ticket_to_dict(
        __import__("services.rfp.store", fromlist=["get_ticket"]).get_ticket(ticket_id)
    )
    assert detail["status"] != STATUS_DONE


def test_http_sunset_requires_mariana_before_final_document(client: TestClient) -> None:
    depts = ["marketing", "operaciones", "procurement"]
    ticket_id = _seed_ticket(
        departments=depts,
        requires_ceo=True,
        metadata={
            "client_name": "Sunset Bay Resorts, LLC",
            "estimated_contract_value_usd": 75_000,
        },
        drafts=ANDES_DRAFTS,
    )
    client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    for dept, owner in {
        "marketing": "Camila Ospina",
        "operaciones": "Felipe Guerrero",
        "procurement": "Lucía Fernández",
    }.items():
        res = client.post(
            f"/rfp/tickets/{ticket_id}/approvals",
            json={"department_id": dept, "decision": "approved", "approver": owner},
        )
        assert res.status_code == 200, res.text
    blocked = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert blocked.status_code == 409
    ceo = client.post(
        f"/rfp/tickets/{ticket_id}/approvals",
        json={
            "department_id": "ceo",
            "decision": "approved",
            "approver": "Mariana Restrepo",
        },
    )
    assert ceo.status_code == 200, ceo.text
    assert ceo.json()["status"] == STATUS_DONE
    doc = client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert doc.status_code == 200
    assert "Mariana Restrepo" in doc.json()["markdown"]


def test_part3_queue_and_ui_page_exist(client: TestClient) -> None:
    assert UI_PAGE.is_file()
    html = UI_PAGE.read_text(encoding="utf-8")
    assert "Camila Ospina" in html
    assert "Mariana Restrepo" in html
    assert "/rfp/tickets/" in html
    queue = client.get("/rfp/part3/queue")
    assert queue.status_code == 200
    assert "queue" in queue.json()


def test_final_document_sqlmodel_table_not_tinydb() -> None:
    assert RfpFinalDocument.__tablename__ == "rfp_final_documents"
    for col in ("ticket_id", "sections_json", "total_estimated_value", "generated_at"):
        assert hasattr(RfpFinalDocument, col)
