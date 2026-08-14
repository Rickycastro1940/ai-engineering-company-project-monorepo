"""Evaluate: Part 2 consumes Part 1 routing handoff only (no PDF reparse)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.constants import STATUS_DISCARDED, STATUS_INTAKE_COMPLETE
from data.pipelines.rfp_intake.routing import route_intake_to_part2
from data.pipelines.rfp_response import (
    PRIMARY_GENERATOR_INPUT,
    Part1HandoffNotReady,
    assert_part1_routing_ready,
    run_response_for_ticket,
    run_response_pipeline,
    synthesizer_payload_from_handoff,
)
from data.pipelines.rfp_response.generator import generate_department_draft
from services.rfp import router as rfp_router
from services.rfp.store import init_db, load_ready_part2_handoff, reset_engine

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
RESPONSE = REPO / "data" / "pipelines" / "rfp_response"
HANDOFF_DOC = REPO / "data" / "pipelines" / "rfp_intake" / "PART2_HANDOFF.md"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'handoff-p2.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_part2_package_does_not_reparse_or_rewrite_intake() -> None:
    for path in RESPONSE.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "import markitdown" not in src.casefold()
        assert "from markitdown" not in src.casefold()
        assert "convert_document_to_markdown" not in src
        assert "classifier_agent" not in src or path.name == "handoff_consume.py"
    # Must consume Part 1 routing helpers, not reinvent classification
    consume = (RESPONSE / "handoff_consume.py").read_text(encoding="utf-8")
    assert "validate_part2_handoff" in consume
    assert "STATUS_INTAKE_COMPLETE" in consume
    assert "part2_ready" in consume
    assert "part2_handoff_json" in consume
    assert HANDOFF_DOC.is_file()
    doc = HANDOFF_DOC.read_text(encoding="utf-8")
    assert "part2_ready" in doc
    assert "part2_handoff_json" in doc
    assert "run_response_for_ticket" in doc


def test_assert_ready_requires_intake_complete_and_flag() -> None:
    with pytest.raises(Part1HandoffNotReady, match="intake_complete"):
        assert_part1_routing_ready(
            ticket_id="t1",
            status="analyzing",
            part2_ready=True,
            handoff={
                "ticket_id": "t1",
                "work_streams": [
                    {"department_id": "marketing", "key_aspects": ["x"]}
                ],
            },
        )
    with pytest.raises(Part1HandoffNotReady, match="part2_ready"):
        assert_part1_routing_ready(
            ticket_id="t1",
            status=STATUS_INTAKE_COMPLETE,
            part2_ready=False,
            handoff={
                "ticket_id": "t1",
                "status": STATUS_INTAKE_COMPLETE,
                "part2_ready": False,
                "reparse_pdf_required": False,
                "work_streams": [
                    {"department_id": "marketing", "key_aspects": ["brand terms"]}
                ],
            },
        )


def test_assert_ready_requires_key_aspects_workstreams() -> None:
    with pytest.raises(Part1HandoffNotReady, match="key_aspects"):
        assert_part1_routing_ready(
            ticket_id="t1",
            status=STATUS_INTAKE_COMPLETE,
            part2_ready=True,
            handoff={
                "ticket_id": "t1",
                "status": STATUS_INTAKE_COMPLETE,
                "part2_ready": True,
                "reparse_pdf_required": False,
                "work_streams": [{"department_id": "marketing", "key_aspects": []}],
            },
        )


def test_assert_ready_forbids_pdf_reparse_flag() -> None:
    with pytest.raises(Part1HandoffNotReady, match="reparse"):
        assert_part1_routing_ready(
            ticket_id="t1",
            status=STATUS_INTAKE_COMPLETE,
            part2_ready=True,
            handoff={
                "ticket_id": "t1",
                "status": STATUS_INTAKE_COMPLETE,
                "part2_ready": True,
                "reparse_pdf_required": True,
                "work_streams": [
                    {"department_id": "marketing", "key_aspects": ["x"]}
                ],
            },
        )


def test_synthesizer_payload_excludes_pdf_as_primary_input() -> None:
    payload = synthesizer_payload_from_handoff(
        {
            "ticket_id": "t1",
            "metadata": {
                "client_name": "Acme",
                "source_pdf_path": "data/raw/rfp/t1/x.pdf",
            },
            "source_pdf_path": "data/raw/rfp/t1/x.pdf",
            "work_streams": [
                {"department_id": "marketing", "key_aspects": ["Brand exclusivity"]}
            ],
            "synthesizer": {"departments_for_drafting": ["marketing"]},
        }
    )
    assert payload["primary_input"] == PRIMARY_GENERATOR_INPUT
    assert "source_pdf_path" not in payload["metadata"]
    assert payload["source_pdf_path_audit_only"] == "data/raw/rfp/t1/x.pdf"
    assert payload["work_streams"][0]["key_aspects"] == ["Brand exclusivity"]


def test_generator_rejects_pdf_kwargs_and_empty_key_aspects() -> None:
    with pytest.raises(TypeError, match="raw PDF"):
        generate_department_draft(
            department_id="marketing",
            metadata={"client_name": "Acme"},
            key_aspects=["Brand exclusivity for Acme"],
            pdf_path="/tmp/rfp.pdf",
        )
    with pytest.raises(TypeError, match="raw PDF"):
        generate_department_draft(
            department_id="marketing",
            metadata={"client_name": "Acme"},
            key_aspects=["Brand exclusivity for Acme"],
            markdown_text="# leaked markdown from PDF",
        )
    with pytest.raises(ValueError, match="key_aspects"):
        generate_department_draft(
            department_id="marketing",
            metadata={"client_name": "Acme"},
            key_aspects=[],
        )


def test_pipeline_uses_part1_route_handoff_key_aspects_not_parallel_summary() -> None:
    intake = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    handoff = route_intake_to_part2(
        ticket_id="consume-1",
        intake_result=intake,
        source_pdf_path="data/raw/rfp/consume-1/file.pdf",
    )
    assert handoff is not None
    assert handoff["ticket_id"] == "consume-1"
    assert handoff["status"] == STATUS_INTAKE_COMPLETE
    assert handoff["part2_ready"] is True
    assert handoff["reparse_pdf_required"] is False

    payload = synthesizer_payload_from_handoff(handoff)
    assert payload["work_streams"]
    assert payload["primary_input"] == PRIMARY_GENERATOR_INPUT
    for stream in payload["work_streams"]:
        assert stream["key_aspects"] == intake.sections[stream["department_id"]]

    # Prove PDF converter is never touched during Part 2 generation
    with patch("markitdown.MarkItDown", side_effect=AssertionError("PDF re-ingest")):
        result = run_response_pipeline(
            ticket_id="consume-1",
            handoff=handoff,
            intake_status=STATUS_INTAKE_COMPLETE,
            part2_ready=True,
        )
    assert result.error_message is None
    assert result.all_passed is True
    load = next(e for e in result.trace if e["node"] == "load_handoff")
    assert load["payload"]["source"] == "part1_handoff_contract"
    assert load["payload"]["primary_input"] == PRIMARY_GENERATOR_INPUT
    assert load["payload"]["queue_flag"] == "part2_ready"
    assert load["payload"]["db_field"] == "part2_handoff_json"
    assert load["payload"]["reparse_pdf_required"] is False
    gen = [e for e in result.trace if e["node"] == "generate_evaluate_sections"]
    assert gen
    assert all(e["payload"]["input"] == "part1_work_stream_key_aspects" for e in gen)


def test_discarded_ticket_not_in_part2_ready_path(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-3.pdf"
    with pdf.open("rb") as fh:
        body = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    assert body["status"] == STATUS_DISCARDED
    assert body.get("part2_ready") is False
    res = client.post(f"/rfp/tickets/{body['ticket_id']}/generate-response")
    assert res.status_code == 409
    detail = res.json()["detail"].casefold()
    assert "part2_ready" in detail or "intake_complete" in detail


def test_http_generate_uses_load_ready_handoff(client: TestClient) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    assert created["status"] == STATUS_INTAKE_COMPLETE
    assert created["part2_ready"] is True

    handoff, status, ready = load_ready_part2_handoff(ticket_id)
    assert status == STATUS_INTAKE_COMPLETE
    assert ready is True
    assert handoff["ticket_id"] == ticket_id
    assert all(ws["key_aspects"] for ws in handoff["work_streams"])

    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["part2_pipeline"]["all_passed"] is True
    assert body["status"] in {"waiting_for_approval", "needs_human_review"}
    load = next(
        e for e in body["part2_pipeline"]["trace"] if e["node"] == "load_handoff"
    )
    assert load["payload"]["source"] == "part1_handoff_contract"
    assert load["payload"]["primary_input"] == PRIMARY_GENERATOR_INPUT
    assert load["payload"]["queue_flag"] == "part2_ready"
    assert load["payload"]["db_field"] == "part2_handoff_json"


def test_canonical_run_response_for_ticket_entry(client: TestClient) -> None:
    """run_response_for_ticket loads queue flag + DB handoff (no PDF)."""
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    with patch("markitdown.MarkItDown", side_effect=AssertionError("PDF re-ingest")):
        result = run_response_for_ticket(ticket_id)
    assert result.error_message is None
    assert result.all_passed is True
    load = next(e for e in result.trace if e["node"] == "load_handoff")
    assert load["payload"]["primary_input"] == PRIMARY_GENERATOR_INPUT
