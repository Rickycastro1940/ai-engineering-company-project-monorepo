"""Evaluate: the ticket reflects generation and evaluation progress in real time.

CONTEXT §2.3 statuses must be written to the same Part 1 ticket row as work
runs — ``drafting`` then ``under_evaluation`` — not only after the pipeline
finishes. Finished department drafts/evals must appear on GET while others
may still be running.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_OWNERS,
    STATUS_DRAFTING,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_UNDER_EVALUATION,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_intake.context_rules import read_context_company_md
from data.pipelines.rfp_response.evaluators import DimensionResult, EvaluationResult
from data.pipelines.rfp_response.loop import SectionLoopResult
from services.rfp import router as rfp_router
from services.rfp.store import (
    get_ticket,
    init_db,
    list_sections,
    reset_engine,
    ticket_to_dict,
)

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
GRAPH_SRC = REPO / "data" / "pipelines" / "rfp_response" / "graph.py"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'realtime.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    reset_engine()
    init_db()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def _ok_eval(department_id: str) -> EvaluationResult:
    return EvaluationResult(
        department_id=department_id,
        passed=True,
        readability=DimensionResult("readability", True, 1.0),
        relevance=DimensionResult("relevance", True, 1.0),
        compliance=DimensionResult("compliance", True, 1.0),
        parallel=True,
        evaluator_agents=[
            "readability_evaluator_agent",
            "relevance_evaluator_agent",
            "compliance_evaluator_agent",
        ],
    )


def test_context_part2_statuses_are_drafting_then_under_evaluation() -> None:
    text = read_context_company_md()
    block = text.split("### 2.3")[1].split("### 2.4")[0]
    assert "`drafting`" in block
    assert "`under_evaluation`" in block
    assert "`needs_human_review`" in block
    assert "`waiting_for_approval`" in block
    src = GRAPH_SRC.read_text(encoding="utf-8")
    assert "STATUS_DRAFTING" in src
    assert "STATUS_UNDER_EVALUATION" in src
    assert "_persist_ticket_progress" in src
    assert "as_completed" in src
    assert "section_results=[item[0].to_dict()]" in src


def test_persist_calls_drafting_before_evaluation_before_terminal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    assert created["status"] == STATUS_INTAKE_COMPLETE

    import services.rfp.store as store_mod

    calls: list[dict] = []
    original = store_mod.persist_part2_progress

    def spy(tid: str, *, status: str, section_results=None):
        ticket = get_ticket(tid)
        calls.append(
            {
                "status": status,
                "db_status_before": ticket.status if ticket else None,
                "section_depts": [
                    s.get("department_id") for s in (section_results or [])
                ],
            }
        )
        return original(tid, status=status, section_results=section_results)

    monkeypatch.setattr(store_mod, "persist_part2_progress", spy)

    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert res.status_code == 200, res.text
    statuses = [c["status"] for c in calls]
    assert STATUS_DRAFTING in statuses
    assert STATUS_UNDER_EVALUATION in statuses
    assert statuses.index(STATUS_DRAFTING) < statuses.index(STATUS_UNDER_EVALUATION)
    terminal = res.json()["status"]
    assert terminal in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}
    assert terminal in statuses

    stored = ticket_to_dict(get_ticket(ticket_id))  # type: ignore[arg-type]
    history = stored["part2_status_history"]
    assert history[0] == STATUS_INTAKE_COMPLETE
    assert STATUS_DRAFTING in history
    assert STATUS_UNDER_EVALUATION in history
    assert history[-1] == stored["status"] == terminal


def test_get_ticket_sees_drafting_and_under_evaluation_during_run(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Poll GET /tickets/{id} while generate-response is in flight."""
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]

    import data.pipelines.rfp_response.graph as graph_mod

    orig = graph_mod._persist_ticket_progress

    def slow_persist(tid: str, status: str, section_results=None) -> None:
        orig(tid, status, section_results)
        if status in {STATUS_DRAFTING, STATUS_UNDER_EVALUATION} and not section_results:
            time.sleep(0.12)

    monkeypatch.setattr(graph_mod, "_persist_ticket_progress", slow_persist)

    seen: list[str] = []
    stop = threading.Event()

    def poll() -> None:
        while not stop.wait(0.02):
            ticket = get_ticket(ticket_id)
            if ticket is not None:
                seen.append(ticket.status)
            r = client.get(f"/rfp/tickets/{ticket_id}")
            if r.status_code == 200:
                seen.append(r.json()["status"])

    thread = threading.Thread(target=poll, daemon=True)
    thread.start()
    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    stop.set()
    thread.join(timeout=3)
    assert res.status_code == 200, res.text
    assert STATUS_DRAFTING in seen
    assert STATUS_UNDER_EVALUATION in seen
    assert get_ticket(ticket_id).status == res.json()["status"]  # type: ignore[union-attr]


def test_finished_department_draft_visible_while_another_still_runs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = SEEDS / "CONTEXT-brasaland-request-2.pdf"
    with pdf.open("rb") as fh:
        created = client.post(
            "/rfp/tickets", files={"file": (pdf.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]

    import data.pipelines.rfp_response.graph as graph_mod

    seen_marketing_while_others_running: list[bool] = []

    def delayed_loop(*, summary, max_iterations=2, **_kwargs):
        dept = summary.department_id
        if dept == "marketing":
            time.sleep(0.05)
        else:
            time.sleep(0.2)
            rows = {row.department_id: row for row in list_sections(ticket_id)}
            marketing = rows.get("marketing")
            seen_marketing_while_others_running.append(
                bool(marketing and marketing.draft_content)
            )
        return SectionLoopResult(
            department_id=dept,
            owner=DEPARTMENT_OWNERS.get(dept, dept),
            draft_content=f"# live {dept} draft\n",
            evaluation=_ok_eval(dept),
            iterations=1,
            exhausted=False,
            generator_agent=f"{dept}_generator_agent",
            section_status="pending",
            include_in_part3=True,
        )

    monkeypatch.setattr(graph_mod, "run_section_loop", delayed_loop)
    res = client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert res.status_code == 200, res.text
    assert seen_marketing_while_others_running
    assert any(seen_marketing_while_others_running)
    ticket = get_ticket(ticket_id)
    assert ticket is not None
    assert ticket.status in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}
    final = {row.department_id: row for row in list_sections(ticket_id)}
    assert final["marketing"].draft_content
    assert final["operaciones"].draft_content
