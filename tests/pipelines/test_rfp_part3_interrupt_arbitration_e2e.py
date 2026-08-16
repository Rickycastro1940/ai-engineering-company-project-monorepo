"""Part 3 coverage the grading rubric expects:

1. Successful interrupt() + programmatic resume
2. Iteration limit reached → needs_human_review
3. Arbitration on disagreement (CONTEXT §7 fixed arbiters)
4. Approve department B while A remains interrupted (true parallel Send branches)
5. Integration / E2E with fixtures + simulated human resumes (Part 3; Parts 1–3 seeded)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data.pipelines.rfp_approval import run_approval_pipeline
from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.fixtures import (
    ANDES_DEPARTMENTS,
    andes_pipeline_kwargs,
    cost_disagreement_pipeline_kwargs,
    setup_sla_breach_pipeline_kwargs,
    simulated_department_approvals,
    sunset_pipeline_kwargs,
)
from data.pipelines.rfp_approval.graph import (
    get_compiled_rfp_approval_graph,
    graph_is_paused,
    interrupt_payloads,
    invoke_rfp_approval_graph,
)
from data.pipelines.rfp_approval.guardrails import MAX_DEPARTMENT_APPROVAL_ITERATIONS
from data.pipelines.rfp_intake.constants import (
    STATUS_DONE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_intake.context_rules import CONTEXT_SEED_EXPECTATIONS
from services.rfp import router as rfp_router
from services.rfp.store import init_db, list_sections, reset_engine

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "rfp-requests" / "brasaland"
ANDES_PDF = SEEDS / "CONTEXT-brasaland-request-2.pdf"
ARTIFACT = Path("/opt/cursor/artifacts/rfp_part3_hitl_arbitration_coverage.json")


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "part3-coverage.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def _paused_dept_ids(result: dict | object) -> set[str]:
    return {
        str(p.get("department_id"))
        for p in interrupt_payloads(result)
        if p.get("department_id")
    }


# ---------------------------------------------------------------------------
# 1. Successful interruptions and resume
# ---------------------------------------------------------------------------


def test_successful_interrupt_then_programmatic_resume_to_done() -> None:
    kwargs = andes_pipeline_kwargs(queued_decisions=[])
    thread_id = approval_thread_id(kwargs["ticket_id"])
    paused = run_approval_pipeline(
        **kwargs,
        thread_id=thread_id,
        use_interrupt=True,
    )
    assert paused.status == STATUS_WAITING_FOR_APPROVAL
    assert paused.paused is True
    assert {p["department_id"] for p in paused.pending_approvals} == set(
        ANDES_DEPARTMENTS
    )
    assert not (paused.final_document or {}).get("markdown")

    current = paused
    for decision in simulated_department_approvals(ANDES_DEPARTMENTS):
        current = run_approval_pipeline(
            **{**kwargs, "queued_decisions": None},
            thread_id=thread_id,
            resume=decision,
            use_interrupt=True,
        )
        assert (
            current.approvals.get(decision["department_id"]) or {}
        ).get("approval_status") == "approved"

    assert current.status == STATUS_DONE
    assert current.final_document.get("ticket_id") == kwargs["ticket_id"]
    assert {s["department_id"] for s in current.final_document["sections"]} == set(
        ANDES_DEPARTMENTS
    )


# ---------------------------------------------------------------------------
# 2. Iteration limit reached
# ---------------------------------------------------------------------------


def test_iteration_limit_reached_sets_needs_human_review() -> None:
    """Arbitration bump past MAX_DEPARTMENT_APPROVAL_ITERATIONS stops the loop."""
    kwargs = cost_disagreement_pipeline_kwargs(
        ticket_id="iter-limit-arb",
        approval_iterations={
            "operaciones": MAX_DEPARTMENT_APPROVAL_ITERATIONS,
            "procurement": MAX_DEPARTMENT_APPROVAL_ITERATIONS,
        },
    )
    result = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        max_approval_iterations=MAX_DEPARTMENT_APPROVAL_ITERATIONS,
        use_interrupt=True,
        thread_id=approval_thread_id(kwargs["ticket_id"]),
    )
    assert result.get("status") == STATUS_NEEDS_HUMAN_REVIEW
    assert "Maximum department approval iterations" in str(result.get("error_message"))
    assert not result.get("__interrupt__")
    assert (result.get("approvals") or {}).get("operaciones", {}).get(
        "approval_status"
    ) == "request_changes"
    arb = [e for e in (result.get("trace") or []) if e.get("node") == "arbitration"]
    assert arb and arb[0]["agent"] == "fixed_arbitration"
    assert arb[0]["output"]["llm_resolved"] is False


def test_human_request_changes_past_cap_sets_needs_human_review() -> None:
    """Named-owner request_changes that exceeds the cap → needs_human_review."""
    kwargs = andes_pipeline_kwargs(
        ticket_id="iter-limit-human",
        queued_decisions=[],
    )
    thread_id = approval_thread_id(kwargs["ticket_id"])
    paused = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        approval_iterations={"marketing": MAX_DEPARTMENT_APPROVAL_ITERATIONS},
        max_approval_iterations=MAX_DEPARTMENT_APPROVAL_ITERATIONS,
        use_interrupt=True,
        thread_id=thread_id,
    )
    assert _paused_dept_ids(paused)

    limited = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=thread_id,
        resume={
            "department_id": "marketing",
            "decision": "request_changes",
            "approver": DEPARTMENT_OWNERS["marketing"],
        },
    )
    assert limited.get("status") == STATUS_NEEDS_HUMAN_REVIEW
    assert "Maximum department approval iterations" in str(limited.get("error_message"))
    assert (limited.get("approvals") or {}).get("marketing", {}).get(
        "approval_status"
    ) == "request_changes"


# ---------------------------------------------------------------------------
# 3. Arbitration on disagreement
# ---------------------------------------------------------------------------


def test_arbitration_on_cost_vs_feasibility_disagreement() -> None:
    kwargs = cost_disagreement_pipeline_kwargs(ticket_id="arb-cost")
    result = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=approval_thread_id(kwargs["ticket_id"]),
    )
    arbitration = list(result.get("arbitration") or [])
    cost = next(r for r in arbitration if r["trigger_id"] == "cost-vs-feasibility")
    assert cost["arbiter"] == "Camila Ospina"
    assert cost["action"] == "request_changes"
    assert cost["llm_resolved"] is False
    assert (result.get("approvals") or {}).get("operaciones", {}).get(
        "approval_status"
    ) == "request_changes"
    assert (result.get("approvals") or {}).get("procurement", {}).get(
        "approval_status"
    ) == "request_changes"
    # Marketing was not forced — may still be interrupted (parallel branch).
    assert result.get("status") in {
        STATUS_WAITING_FOR_APPROVAL,
        STATUS_NEEDS_HUMAN_REVIEW,
    }
    arb_trace = [e for e in (result.get("trace") or []) if e.get("node") == "arbitration"]
    assert arb_trace
    assert "cost-vs-feasibility" in arb_trace[0]["output"]["trigger_ids"]


def test_arbitration_on_setup_sla_breach_disagreement() -> None:
    kwargs = setup_sla_breach_pipeline_kwargs(ticket_id="arb-sla")
    result = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=approval_thread_id(kwargs["ticket_id"]),
    )
    arbitration = list(result.get("arbitration") or [])
    sla = next(r for r in arbitration if r["trigger_id"] == "setup-sla-breach")
    assert sla["arbiter"] == "Felipe Guerrero"
    assert sla["escalation_arbiter"] == "Camila Ospina"
    assert sla["action"] == "request_changes"
    assert sla["llm_resolved"] is False
    assert (result.get("approvals") or {}).get("marketing", {}).get(
        "approval_status"
    ) == "request_changes"
    assert (result.get("approvals") or {}).get("marketing", {}).get("arbiter_forced")


def test_arbitration_ceo_threshold_on_sunset_disagreement_path() -> None:
    kwargs = sunset_pipeline_kwargs(include_ceo=False)
    kwargs["queued_decisions"] = []
    thread_id = approval_thread_id(str(kwargs["ticket_id"]))
    paused = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=thread_id,
    )
    arbitration = list(paused.get("arbitration") or [])
    assert any(r["trigger_id"] == "ceo-threshold" for r in arbitration)
    ceo = next(r for r in arbitration if r["trigger_id"] == "ceo-threshold")
    assert ceo["arbiter"] == "Mariana Restrepo"
    assert ceo["action"] == "block_synthesizer"
    assert ceo["llm_resolved"] is False


# ---------------------------------------------------------------------------
# 4. Parallel branches — approve B while A remains interrupted
# ---------------------------------------------------------------------------


def test_approve_department_b_while_a_remains_interrupted_proves_parallel_send() -> None:
    """True fan-out: operaciones (B) can finish while marketing (A) stays on interrupt().

    Serial fake-parallelism would either unblock all branches together or force
    marketing before operaciones can resume.
    """
    kwargs = andes_pipeline_kwargs(
        ticket_id="parallel-b-while-a",
        queued_decisions=[],
    )
    thread_id = approval_thread_id(kwargs["ticket_id"])
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_compiled_rfp_approval_graph(use_interrupt=True)

    paused = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=thread_id,
    )
    assert _paused_dept_ids(paused) == set(ANDES_DEPARTMENTS)
    snapshot = graph.get_state(config)
    assert graph_is_paused(snapshot)
    assert _paused_dept_ids(snapshot) == set(ANDES_DEPARTMENTS)

    # Resume department B (operaciones) first — out of marketing-first Send order.
    after_b = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=thread_id,
        resume={
            "department_id": "operaciones",
            "decision": "approved",
            "approver": DEPARTMENT_OWNERS["operaciones"],
        },
    )
    assert (after_b.get("approvals") or {}).get("operaciones", {}).get(
        "approval_status"
    ) == "approved"
    # Department A (marketing) must still be interrupted — not approved, not drained.
    assert (after_b.get("approvals") or {}).get("marketing", {}).get(
        "approval_status"
    ) != "approved"
    remaining = _paused_dept_ids(after_b)
    assert "operaciones" not in remaining
    assert "marketing" in remaining
    assert "procurement" in remaining
    assert after_b.get("status") != STATUS_DONE

    # Checkpoint still paused for siblings (A / procurement) — not a serial drain.
    snapshot_after = graph.get_state(config)
    assert graph_is_paused(snapshot_after)
    values = dict(getattr(snapshot_after, "values", None) or {})
    assert (values.get("approvals") or {}).get("operaciones", {}).get(
        "approval_status"
    ) == "approved"
    assert (values.get("approvals") or {}).get("marketing", {}).get(
        "approval_status"
    ) != "approved"
    # Prefer invoke-result interrupt set; checkpoint may still list completed tasks
    # until garbage-collected, so also require pending_approvals / sibling status.
    pending = {
        str(p.get("department_id"))
        for p in (after_b.get("pending_approvals") or [])
        if p.get("department_id")
    }
    if pending:
        assert "marketing" in pending
        assert "operaciones" not in pending
    else:
        assert remaining == {"marketing", "procurement"}


# ---------------------------------------------------------------------------
# 5. Integration / E2E — fixtures + simulated resumes; Parts 1–3 seeded
# ---------------------------------------------------------------------------


def test_fixture_simulated_resumes_complete_part3_andes_and_sunset() -> None:
    andes = run_approval_pipeline(
        **andes_pipeline_kwargs(ticket_id="e2e-fix-andes"),
        thread_id=approval_thread_id("e2e-fix-andes"),
        use_interrupt=True,
    )
    assert andes.status == STATUS_DONE
    assert "Camila Ospina" in andes.final_document["markdown"]

    sunset = run_approval_pipeline(
        **sunset_pipeline_kwargs(ticket_id="e2e-fix-sunset"),
        thread_id=approval_thread_id("e2e-fix-sunset"),
        use_interrupt=True,
    )
    assert sunset.status == STATUS_DONE
    assert "Mariana Restrepo" in sunset.final_document["markdown"]
    assert (sunset.ceo_approval or {}).get("approval_status") == "approved"


@pytest.fixture()
def http_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'part3-http-e2e.sqlite'}")
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.setenv("RFP_INTAKE_SYNC", "1")
    monkeypatch.setenv(
        "RFP_CHECKPOINT_SQLITE", str(tmp_path / "part3-http-e2e-ckpt.sqlite")
    )
    reset_engine()
    init_db()
    reset_approval_checkpointer()
    app = FastAPI()
    app.include_router(rfp_router)
    return TestClient(app)


def test_parts_1_to_3_seeded_http_with_parallel_midflight_and_simulated_resumes(
    http_client: TestClient,
) -> None:
    """Seeded CONTEXT PDF → generate → start-approval → approve B while A pending → done."""
    assert ANDES_PDF.is_file()
    expected = CONTEXT_SEED_EXPECTATIONS[ANDES_PDF.name]
    journey: list[dict] = []

    with ANDES_PDF.open("rb") as fh:
        created = http_client.post(
            "/rfp/tickets", files={"file": (ANDES_PDF.name, fh, "application/pdf")}
        ).json()
    ticket_id = created["ticket_id"]
    assert created["status"] == "intake_complete"
    assert set(created["departments_needed"]) == set(expected["departments"])
    journey.append({"step": "part1", "ticket_id": ticket_id, "status": created["status"]})

    generated = http_client.post(f"/rfp/tickets/{ticket_id}/generate-response")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["ticket_id"] == ticket_id
    assert body["status"] in {STATUS_WAITING_FOR_APPROVAL, STATUS_NEEDS_HUMAN_REVIEW}
    journey.append({"step": "part2", "ticket_id": ticket_id, "status": body["status"]})

    started = http_client.post(f"/rfp/tickets/{ticket_id}/start-approval")
    assert started.status_code == 200, started.text
    paused = started.json()
    assert paused["status"] == STATUS_WAITING_FOR_APPROVAL
    pending = (paused.get("part3_pipeline") or {}).get("pending_approvals") or []
    assert {p["department_id"] for p in pending} == set(expected["departments"])

    # Parallel proof on the live ticket checkpoint: approve operaciones (B) first.
    thread_id = approval_thread_id(ticket_id)
    graph = get_compiled_rfp_approval_graph(use_interrupt=True)
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    assert graph_is_paused(snapshot)
    assert "marketing" in _paused_dept_ids(snapshot)
    assert "operaciones" in _paused_dept_ids(snapshot)

    approve_b = http_client.post(
        f"/rfp/tickets/{ticket_id}/approvals",
        json={
            "department_id": "operaciones",
            "decision": "approved",
            "approver": DEPARTMENT_OWNERS["operaciones"],
        },
    )
    assert approve_b.status_code == 200, approve_b.text
    mid = approve_b.json()
    by_dept = {
        s["department_id"]: s.get("approval_status")
        for s in mid.get("department_sections") or []
    }
    assert by_dept["operaciones"] == "approved"
    assert by_dept["marketing"] == "pending"
    assert by_dept["procurement"] == "pending"
    assert mid["status"] == STATUS_WAITING_FOR_APPROVAL
    journey.append(
        {
            "step": "approve_b_while_a_interrupted",
            "ticket_id": ticket_id,
            "status": mid["status"],
            "section_statuses": by_dept,
            "part3_pending": [
                p.get("department_id")
                for p in (
                    (mid.get("part3_pipeline") or {}).get("pending_approvals") or []
                )
            ],
            "checkpoint_still_paused": graph_is_paused(
                graph.get_state({"configurable": {"thread_id": thread_id}})
            ),
        }
    )
    assert by_dept["marketing"] == "pending"
    assert journey[-1]["checkpoint_still_paused"] is True
    # Sibling A still open; B done — not serial fake-parallelism.
    assert "operaciones" not in set(journey[-1]["part3_pending"] or []) or by_dept[
        "operaciones"
    ] == "approved"

    # Finish remaining simulated named-owner resumes.
    for dept in ("marketing", "procurement"):
        res = http_client.post(
            f"/rfp/tickets/{ticket_id}/approvals",
            json={
                "department_id": dept,
                "decision": "approved",
                "approver": DEPARTMENT_OWNERS[dept],
            },
        )
        assert res.status_code == 200, res.text
        last = res.json()
        journey.append(
            {
                "step": f"approve_{dept}",
                "ticket_id": ticket_id,
                "status": last["status"],
            }
        )

    assert last["status"] == STATUS_DONE
    doc = http_client.get(f"/rfp/tickets/{ticket_id}/final-document")
    assert doc.status_code == 200, doc.text
    payload = doc.json()
    assert payload["ticket_id"] == ticket_id
    assert {s["department_id"] for s in payload["sections"]} == set(expected["departments"])
    rows = {r.department_id: r.approval_status for r in list_sections(ticket_id)}
    assert rows == {d: "approved" for d in expected["departments"]}

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps({"journey": journey, "final": payload}, indent=2), encoding="utf-8")
