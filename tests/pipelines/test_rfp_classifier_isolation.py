"""Evaluate: Classifier rejects non-RFPs without stopping other tickets.

Discard is per-ticket: status=discarded + discard_reason on that ticket only.
Other tickets keep analyzing / complete independently (no process halt, no global lock).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import classifier_agent, convert_document_to_markdown, run_intake_pipeline
from data.pipelines.rfp_intake.constants import (
    STATUS_ANALYZING,
    STATUS_DISCARDED,
    STATUS_INTAKE_COMPLETE,
)
from services.rfp import router as rfp_router
from services.rfp.store import get_ticket, init_db, list_part2_queue, list_tickets, reset_engine

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
FORMAL = SEEDS / "CONTEXT-brasaland-request-1.pdf"
INFORMAL = SEEDS / "CONTEXT-brasaland-request-2.pdf"
INVALID = SEEDS / "CONTEXT-brasaland-request-3.pdf"


def test_classifier_discard_returns_decision_does_not_raise() -> None:
    """Non-RFP reject is a soft discard outcome — not an exception that aborts the app."""
    md = convert_document_to_markdown(INVALID)
    decision = classifier_agent(md)
    assert decision.is_valid_rfp is False
    assert decision.discard_reason
    # Subsequent classification of a valid RFP still works in the same process
    ok = classifier_agent(convert_document_to_markdown(FORMAL))
    assert ok.is_valid_rfp is True


def test_pipeline_discard_then_accept_in_same_process() -> None:
    discarded = run_intake_pipeline(pdf_path=INVALID)
    assert discarded.status == STATUS_DISCARDED
    assert discarded.discard_reason

    accepted = run_intake_pipeline(pdf_path=INFORMAL)
    assert accepted.status == STATUS_INTAKE_COMPLETE
    assert accepted.departments_needed
    assert accepted.discard_reason is None


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'isol.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


@pytest.fixture()
def async_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("RFP_INTAKE_SYNC", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'isol-async.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    reset_engine()
    init_db()
    scheduled: list[tuple] = []

    def _capture(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(BackgroundTasks, "add_task", _capture)
    app = FastAPI()
    app.include_router(rfp_router)
    client = TestClient(app)
    client.scheduled_jobs = scheduled  # type: ignore[attr-defined]
    return client


def _upload(client: TestClient, pdf: Path) -> dict:
    with pdf.open("rb") as fh:
        res = client.post(
            "/rfp/tickets",
            files={"file": (pdf.name, fh, "application/pdf")},
        )
    assert res.status_code == 200, res.text
    return res.json()


def test_http_discard_does_not_block_later_accept(client: TestClient) -> None:
    bad = _upload(client, INVALID)
    assert bad["status"] == STATUS_DISCARDED
    assert bad.get("discard_reason")
    bad_id = bad["ticket_id"]

    good = _upload(client, FORMAL)
    assert good["status"] == STATUS_INTAKE_COMPLETE
    assert good["ticket_id"] != bad_id
    assert "Sunset Bay" in (good.get("metadata") or {}).get("client_name", "")

    # Both tickets coexist with independent statuses
    tickets = {t.ticket_id: t for t in list_tickets()}
    assert tickets[bad_id].status == STATUS_DISCARDED
    assert tickets[good["ticket_id"]].status == STATUS_INTAKE_COMPLETE

    # Discarded ticket is not in Part 2 queue; accepted one is
    queue_ids = {q["ticket_id"] for q in list_part2_queue()}
    assert bad_id not in queue_ids
    assert good["ticket_id"] in queue_ids


def test_discard_between_two_valid_uploads_leaves_both_complete(
    client: TestClient,
) -> None:
    a = _upload(client, FORMAL)
    b = _upload(client, INVALID)
    c = _upload(client, INFORMAL)
    assert a["status"] == STATUS_INTAKE_COMPLETE
    assert b["status"] == STATUS_DISCARDED
    assert c["status"] == STATUS_INTAKE_COMPLETE
    statuses = {t.status for t in list_tickets()}
    assert STATUS_DISCARDED in statuses
    assert STATUS_INTAKE_COMPLETE in statuses
    assert len(list_tickets()) >= 3


def test_async_discard_job_does_not_cancel_other_background_jobs(
    async_client: TestClient,
) -> None:
    """Schedule valid + invalid; running discard job must not prevent valid job."""
    valid = _upload(async_client, FORMAL)
    invalid = _upload(async_client, INVALID)
    assert valid["status"] == STATUS_ANALYZING
    assert invalid["status"] == STATUS_ANALYZING
    jobs = async_client.scheduled_jobs  # type: ignore[attr-defined]
    assert len(jobs) == 2

    # Run invalid job first (discard)
    # jobs[0] is formal, jobs[1] is invalid — run invalid first
    inv_func, inv_args, inv_kwargs = jobs[1]
    inv_func(*inv_args, **inv_kwargs)
    assert get_ticket(invalid["ticket_id"]).status == STATUS_DISCARDED  # type: ignore[union-attr]

    # Valid ticket still analyzing — discard did not flip/clear it
    assert get_ticket(valid["ticket_id"]).status == STATUS_ANALYZING  # type: ignore[union-attr]

    # Run valid job — completes independently
    ok_func, ok_args, ok_kwargs = jobs[0]
    ok_func(*ok_args, **ok_kwargs)
    assert get_ticket(valid["ticket_id"]).status == STATUS_INTAKE_COMPLETE  # type: ignore[union-attr]
    assert get_ticket(invalid["ticket_id"]).status == STATUS_DISCARDED  # type: ignore[union-attr]


def test_discard_response_is_200_not_5xx(client: TestClient) -> None:
    """Rejecting a non-RFP must not look like a server failure for other clients."""
    with INVALID.open("rb") as fh:
        res = client.post(
            "/rfp/tickets",
            files={"file": (INVALID.name, fh, "application/pdf")},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == STATUS_DISCARDED
    # Another client can still upload immediately after
    with INFORMAL.open("rb") as fh:
        res2 = client.post(
            "/rfp/tickets",
            files={"file": (INFORMAL.name, fh, "application/pdf")},
        )
    assert res2.status_code == 200
    assert res2.json()["status"] == STATUS_INTAKE_COMPLETE
