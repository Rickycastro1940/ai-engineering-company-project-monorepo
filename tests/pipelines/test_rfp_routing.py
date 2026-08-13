"""Evaluate: Part 2 routing handoff (ticket_id + synthesizer payload, no second API)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import run_intake_pipeline, route_intake_to_part2
from data.pipelines.rfp_intake.constants import STATUS_DISCARDED, STATUS_INTAKE_COMPLETE
from data.pipelines.rfp_intake.routing import validate_part2_handoff
from services.rfp import router as rfp_router
from services.rfp.store import (
    get_ticket,
    init_db,
    list_part2_queue,
    load_part2_handoff,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
DOC = REPO / "data" / "pipelines" / "rfp_intake" / "PART2_HANDOFF.md"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'routing.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_handoff_contract_documented() -> None:
    assert DOC.is_file()
    text = DOC.read_text(encoding="utf-8")
    assert "ticket_id" in text
    assert "work_streams" in text
    assert "key_aspects" in text
    assert "reparse_pdf_required" in text
    assert "no second" in text.casefold() or "without a\nsecond" in text.casefold() or "second API" in text


def test_route_builds_ticket_id_and_work_streams() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    assert result.status == STATUS_INTAKE_COMPLETE
    contract = route_intake_to_part2(
        ticket_id="demo-ticket-001",
        intake_result=result,
        source_pdf_path="data/raw/rfp/demo/file.pdf",
    )
    assert contract is not None
    validate_part2_handoff(contract)
    assert contract["ticket_id"] == "demo-ticket-001"
    assert contract["part2_ready"] is True
    assert contract["reparse_pdf_required"] is False
    assert contract["work_streams"]
    for stream in contract["work_streams"]:
        assert stream["department_id"]
        assert stream["key_aspects"]
        assert stream["next_action"] == "draft_section"
    assert set(s["department_id"] for s in contract["work_streams"]) == set(
        result.departments_needed
    )


def test_discarded_not_routed_to_part2() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-3.pdf")
    assert result.status == STATUS_DISCARDED
    assert (
        route_intake_to_part2(ticket_id="x", intake_result=result, source_pdf_path="")
        is None
    )


def test_persist_sets_flag_and_queue(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        res = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == STATUS_INTAKE_COMPLETE
    assert body["part2_ready"] is True
    assert body["part2_handoff"]["ticket_id"] == body["ticket_id"]
    assert body["work_streams"]
    assert body["part2_handoff"]["reparse_pdf_required"] is False

    ticket = get_ticket(body["ticket_id"])
    assert ticket is not None
    assert ticket.part2_ready is True
    assert ticket.part2_handoff_json

    queue = list_part2_queue()
    assert any(q["ticket_id"] == body["ticket_id"] for q in queue)

    handoff = load_part2_handoff(body["ticket_id"])
    assert handoff["ticket_id"] == body["ticket_id"]
    # Part 2 can start from key_aspects alone — no PDF bytes required
    assert all(ws["key_aspects"] for ws in handoff["work_streams"])


def test_http_part2_queue_and_handoff_same_api(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]

    queue_res = client.get("/rfp/part2/queue")
    assert queue_res.status_code == 200
    queue = queue_res.json()
    assert queue["count"] >= 1
    assert any(q["ticket_id"] == ticket_id for q in queue["queue"])

    handoff_res = client.get(f"/rfp/tickets/{ticket_id}/part2-handoff")
    assert handoff_res.status_code == 200
    handoff = handoff_res.json()
    assert handoff["ticket_id"] == ticket_id
    assert handoff["schema_version"]
    assert handoff["work_streams"]
    assert handoff["synthesizer"]["departments_for_drafting"]


def test_discarded_ticket_not_in_queue_and_no_handoff(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-3.pdf"
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    assert body["status"] == STATUS_DISCARDED
    assert body.get("part2_ready") is False
    assert not any(q["ticket_id"] == body["ticket_id"] for q in list_part2_queue())
    detail = ticket_to_dict(get_ticket(body["ticket_id"]))  # type: ignore[arg-type]
    assert detail["part2_ready"] is False
    handoff_res = client.get(f"/rfp/tickets/{body['ticket_id']}/part2-handoff")
    assert handoff_res.status_code == 409


def test_no_second_api_service_for_routing() -> None:
    assert not (REPO / "services" / "rfp_part2_api").exists()
    assert not (REPO / "services" / "rfp_routing_api").exists()
    routes = (REPO / "services" / "rfp" / "routes.py").read_text(encoding="utf-8")
    assert "/part2/queue" in routes
    assert "part2-handoff" in routes
