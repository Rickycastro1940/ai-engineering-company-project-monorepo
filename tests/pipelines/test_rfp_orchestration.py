"""Evaluate: department orchestration (orchestrator → workers → synthesizer)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake import run_intake_pipeline
from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_MARKETING,
    DEPARTMENT_OPERACIONES,
    DEPARTMENT_OWNERS,
    DEPARTMENT_PROCUREMENT,
    DEPARTMENT_TRAINING,
    STATUS_INTAKE_COMPLETE,
)
from data.pipelines.rfp_intake.orchestration import (
    DepartmentSubtask,
    build_department_excerpt,
    department_worker,
    orchestrator,
)
from services.rfp import router as rfp_router
from services.rfp.store import get_ticket, init_db, list_sections, reset_engine, ticket_to_dict

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"


def test_orchestrator_decomposes_per_department() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    nodes = [e["node"] for e in result.trace]
    assert "orchestrator" in nodes
    orch = next(e for e in result.trace if e["node"] == "orchestrator")
    assert set(orch["payload"]["subtasks"]) == {
        DEPARTMENT_MARKETING,
        DEPARTMENT_OPERACIONES,
        DEPARTMENT_PROCUREMENT,
        DEPARTMENT_TRAINING,
    }


def test_workers_receive_excerpt_not_full_doc_and_store_key_aspects() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    assert result.status == STATUS_INTAKE_COMPLETE
    assert set(result.sections) == set(result.departments_needed)
    for dept, aspects in result.sections.items():
        assert aspects, f"{dept} missing key_aspects"
        joined = " ".join(aspects).casefold()
        assert "we will charge $" not in joined
        assert "guaranteed 100" not in joined

    worker_events = [e for e in result.trace if e["node"] == "department_worker"]
    assert len(worker_events) == 4
    for event in worker_events:
        assert event["payload"]["excerpt_chars"] > 0
        assert event["payload"]["key_aspects"]


def test_andes_skips_training_worker() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-2.pdf")
    assert DEPARTMENT_TRAINING not in result.departments_needed
    assert DEPARTMENT_TRAINING not in result.sections
    worker_depts = [
        e["payload"]["department_id"]
        for e in result.trace
        if e["node"] == "department_worker"
    ]
    assert DEPARTMENT_TRAINING not in worker_depts


def test_synthesizer_sales_facing_ask_whom_and_part2_handoff() -> None:
    result = run_intake_pipeline(pdf_path=SEEDS / "CONTEXT-brasaland-request-1.pdf")
    assert "SALES-FACING" in result.intake_summary
    assert "What to ask whom" in result.intake_summary
    assert "Camila Ospina" in result.intake_summary
    assert "Felipe Guerrero" in result.intake_summary
    assert result.ask_whom
    assert any(
        a["owner"] == DEPARTMENT_OWNERS[DEPARTMENT_MARKETING] for a in result.ask_whom
    )

    handoff = result.part2_handoff
    assert handoff.get("next_part") == 2
    assert handoff.get("status") == STATUS_INTAKE_COMPLETE
    assert "Part 2" in handoff.get("message", "")
    assert set(handoff.get("departments_for_drafting") or []) == set(
        result.departments_needed
    )
    assert handoff.get("requires_ceo_approval") is True

    nodes = [e["node"] for e in result.trace]
    assert "synthesizer" in nodes


def test_key_aspects_persisted_per_department_sqlmodel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'orch.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    client = TestClient(app)

    pdf = SEEDS / "CONTEXT-brasaland-request-1.pdf"
    with pdf.open("rb") as fh:
        res = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == STATUS_INTAKE_COMPLETE
    assert body["part2_handoff"]["next_part"] == 2

    ticket_id = body["ticket_id"]
    sections = list_sections(ticket_id)
    assert {s.department_id for s in sections} == set(body["departments_needed"])
    for row in sections:
        aspects = json.loads(row.key_aspects_json)
        assert isinstance(aspects, list) and aspects

    detail = ticket_to_dict(get_ticket(ticket_id))  # type: ignore[arg-type]
    assert detail["ask_whom"]
    assert "What to ask whom" in (detail["intake_summary"] or "")


def test_worker_open_questions_when_budget_absent() -> None:
    meta = {
        "client_name": "Acme",
        "scope": "weekly catering",
        "deadline": "2026-09-01",
    }
    excerpt = "Please send a catering proposal for our office team. No budget listed."
    subtask = DepartmentSubtask(
        department_id=DEPARTMENT_PROCUREMENT,
        owner=DEPARTMENT_OWNERS[DEPARTMENT_PROCUREMENT],
        label="Procurement",
        excerpt=excerpt,
        shared_metadata=meta,
    )
    worker = department_worker(subtask)
    assert worker.key_aspects
    assert worker.open_questions, "missing budget must become open_questions — never invent"


def test_orchestrator_helper_builds_excerpts() -> None:
    md = "Brand exclusivity clause.\n\nKitchen staff setup logistics.\n\nBudget USD 10,000."
    tasks = orchestrator(
        markdown_text=md,
        metadata={"client_name": "X"},
        departments_needed=[DEPARTMENT_MARKETING, DEPARTMENT_OPERACIONES],
    )
    assert len(tasks) == 2
    assert tasks[0].excerpt
    assert build_department_excerpt(md, DEPARTMENT_MARKETING)
