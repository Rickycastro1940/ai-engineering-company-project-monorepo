"""Part 2 updates the Part 1 ticket status in PostgreSQL (SQLModel)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake.constants import (
    STATUS_DRAFTING,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_UNDER_EVALUATION,
    STATUS_WAITING_FOR_APPROVAL,
)
from services.rfp import router as rfp_router
from services.rfp.store import (
    get_ticket,
    init_db,
    list_sections,
    persist_part2_progress,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'status.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_persist_part2_progress_advances_intake_complete_ticket(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    assert created["status"] == STATUS_INTAKE_COMPLETE

    assert persist_part2_progress(ticket_id, status=STATUS_DRAFTING) is True
    assert get_ticket(ticket_id).status == STATUS_DRAFTING  # type: ignore[union-attr]

    assert persist_part2_progress(ticket_id, status=STATUS_UNDER_EVALUATION) is True
    assert get_ticket(ticket_id).status == STATUS_UNDER_EVALUATION  # type: ignore[union-attr]

    assert persist_part2_progress(ticket_id, status=STATUS_NEEDS_HUMAN_REVIEW) is True
    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status == STATUS_NEEDS_HUMAN_REVIEW
    history = ticket_to_dict(ticket)["part2_status_history"]
    assert history == [
        STATUS_INTAKE_COMPLETE,
        STATUS_DRAFTING,
        STATUS_UNDER_EVALUATION,
        STATUS_NEEDS_HUMAN_REVIEW,
    ]


def test_generate_response_persists_status_history_drafts_and_evals(
    client: TestClient,
) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    assert created["status"] == STATUS_INTAKE_COMPLETE
    ticket_id = created["ticket_id"]

    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}

    history = body.get("part2_status_history") or []
    assert STATUS_DRAFTING in history
    assert STATUS_UNDER_EVALUATION in history
    assert history[0] == STATUS_INTAKE_COMPLETE
    assert history[-1] == body["status"]
    assert history.index(STATUS_DRAFTING) < history.index(STATUS_UNDER_EVALUATION)

    sections = list_sections(ticket_id)
    assert sections
    for row in sections:
        assert row.draft_content
        assert row.evaluation_results_json
        assert "readability" in row.evaluation_results_json
        assert "relevance" in row.evaluation_results_json
        assert "compliance" in row.evaluation_results_json

    stored = ticket_to_dict(get_ticket(ticket_id))  # type: ignore[arg-type]
    assert stored["status"] == body["status"]
    assert all(s.get("draft_content") for s in stored["department_sections"])
    assert all(s.get("evaluation_results") for s in stored["department_sections"])
