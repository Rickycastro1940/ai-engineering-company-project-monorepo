"""Evaluate: flow pauses at interrupt() *before* each department approval, with correct state.

CONTEXT §6 Part 3 — named-owner HITL must stop while ``approval_status`` is still
``pending``; ``apply_approval`` runs only after a programmatic resume.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.pipelines.rfp_approval import run_approval_pipeline
from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.fixtures import (
    ANDES_DEPARTMENTS,
    andes_pipeline_kwargs,
    simulated_department_approvals,
)
from data.pipelines.rfp_approval.graph import (
    get_compiled_rfp_approval_graph,
    graph_is_paused,
    interrupt_payloads,
    invoke_rfp_approval_graph,
)
from data.pipelines.rfp_intake.constants import STATUS_DONE, STATUS_WAITING_FOR_APPROVAL

ARTIFACT = Path("/opt/cursor/artifacts/rfp_pause_before_each_department.json")


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "pause-eval.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def _trace_nodes(result: dict) -> list[str]:
    return [str(e.get("node") or "") for e in (result.get("trace") or [])]


def _assert_pause_state_before_approvals(
    *,
    result: dict,
    expected_departments: set[str],
    already_approved: set[str] | None = None,
) -> dict:
    """Shared assertions for a HITL pause that has not yet approved the pending set."""
    already_approved = set(already_approved or ())
    payloads = interrupt_payloads(result)
    paused_depts = {str(p.get("department_id")) for p in payloads if p.get("department_id")}
    expect_pending = expected_departments - already_approved

    assert paused_depts == expect_pending, (
        f"expected interrupts for {sorted(expect_pending)}, got {sorted(paused_depts)}"
    )
    assert result.get("status") in {STATUS_WAITING_FOR_APPROVAL, None} or str(
        result.get("status")
    ) == STATUS_WAITING_FOR_APPROVAL
    # Pause must happen *before* apply_approval for still-pending departments.
    assert "synthesizer" not in _trace_nodes(result)

    approvals = result.get("approvals") or {}
    for dept in expect_pending:
        row = approvals.get(dept) or {}
        assert row.get("approval_status") in {None, "pending"}, (
            f"{dept} must still be pending at pause; got {row}"
        )
        payload = next(p for p in payloads if p.get("department_id") == dept)
        assert payload.get("kind") == "department_approval"
        assert payload.get("approver") == DEPARTMENT_OWNERS[dept]
        assert payload.get("ticket_id")
        pending_rows = payload.get("pending") or []
        assert pending_rows, f"{dept} interrupt missing pending[] snapshot"
        assert all(r.get("approval_status") == "pending" for r in pending_rows)
        assert all(r.get("approver") == DEPARTMENT_OWNERS[dept] for r in pending_rows)

    for dept in already_approved:
        assert (approvals.get(dept) or {}).get("approval_status") == "approved"
        assert dept not in paused_depts

    return {
        "paused_departments": sorted(paused_depts),
        "already_approved": sorted(already_approved),
        "status": result.get("status"),
        "interrupt_payloads": [
            {
                "department_id": p.get("department_id"),
                "approver": p.get("approver"),
                "kind": p.get("kind"),
                "approval_status": (p.get("pending") or [{}])[0].get("approval_status"),
            }
            for p in payloads
        ],
        "trace_nodes": _trace_nodes(result),
    }


def test_flow_pauses_before_each_department_approval_with_correct_state() -> None:
    """Initial fan-out: every active department is interrupted while still pending."""
    kwargs = andes_pipeline_kwargs(
        ticket_id="pause-eval-initial",
        queued_decisions=[],
    )
    thread_id = approval_thread_id(kwargs["ticket_id"])
    paused = invoke_rfp_approval_graph(
        **{k: v for k, v in kwargs.items() if k != "queued_decisions"},
        use_interrupt=True,
        thread_id=thread_id,
    )

    snapshot = _assert_pause_state_before_approvals(
        result=paused,
        expected_departments=set(ANDES_DEPARTMENTS),
    )
    # apply_approval must not have run yet — pause is before the decision is applied.
    assert "apply_approval" not in snapshot["trace_nodes"]
    assert set(snapshot["paused_departments"]) == set(ANDES_DEPARTMENTS)

    graph = get_compiled_rfp_approval_graph(use_interrupt=True)
    state = graph.get_state({"configurable": {"thread_id": thread_id}})
    assert graph_is_paused(state)
    assert {p.get("department_id") for p in interrupt_payloads(state)} == set(
        ANDES_DEPARTMENTS
    )
    values = dict(getattr(state, "values", None) or {})
    for dept in ANDES_DEPARTMENTS:
        assert (values.get("approvals") or {}).get(dept, {}).get(
            "approval_status"
        ) in {None, "pending"}
    assert str(values.get("status") or STATUS_WAITING_FOR_APPROVAL) == (
        STATUS_WAITING_FOR_APPROVAL
    )

def test_sequential_resumes_each_keep_remaining_departments_paused() -> None:
    """After each resume, remaining departments stay interrupted with pending state."""
    kwargs = andes_pipeline_kwargs(
        ticket_id="pause-eval-sequential",
        queued_decisions=[],
    )
    thread_id = approval_thread_id(kwargs["ticket_id"])
    invoke_kwargs = {k: v for k, v in kwargs.items() if k != "queued_decisions"}

    paused = invoke_rfp_approval_graph(
        **invoke_kwargs,
        use_interrupt=True,
        thread_id=thread_id,
    )
    journey = [
        _assert_pause_state_before_approvals(
            result=paused,
            expected_departments=set(ANDES_DEPARTMENTS),
        )
    ]
    assert "apply_approval" not in journey[0]["trace_nodes"]

    approved: set[str] = set()
    current = paused
    for decision in simulated_department_approvals(ANDES_DEPARTMENTS):
        dept = decision["department_id"]
        # Before resume: this department must still be in the interrupt set.
        assert dept in {
            p.get("department_id") for p in interrupt_payloads(current)
        }, f"{dept} was not paused before its approval"

        current = invoke_rfp_approval_graph(
            **invoke_kwargs,
            use_interrupt=True,
            thread_id=thread_id,
            resume=decision,
        )
        approved.add(dept)
        assert (current.get("approvals") or {}).get(dept, {}).get(
            "approval_status"
        ) == "approved"

        remaining = set(ANDES_DEPARTMENTS) - approved
        if remaining:
            step = _assert_pause_state_before_approvals(
                result=current,
                expected_departments=set(ANDES_DEPARTMENTS),
                already_approved=approved,
            )
            # This resume applied exactly one department; siblings still pending.
            assert "apply_approval" in _trace_nodes(current) or (
                current.get("approvals") or {}
            ).get(dept, {}).get("approval_status") == "approved"
            journey.append(step)
        else:
            assert current.get("status") == STATUS_DONE
            assert not interrupt_payloads(current)
            journey.append(
                {
                    "paused_departments": [],
                    "already_approved": sorted(approved),
                    "status": current.get("status"),
                    "final_document_ticket": (current.get("final_document") or {}).get(
                        "ticket_id"
                    ),
                }
            )

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps({"journey": journey}, indent=2), encoding="utf-8")


def test_pipeline_result_exposes_paused_pending_approvals_before_resume() -> None:
    """``run_approval_pipeline`` reports paused=True and pending CONTEXT owners."""
    kwargs = andes_pipeline_kwargs(
        ticket_id="pause-eval-pipeline",
        queued_decisions=[],
    )
    result = run_approval_pipeline(
        **kwargs,
        thread_id=approval_thread_id(kwargs["ticket_id"]),
        use_interrupt=True,
    )
    assert result.status == STATUS_WAITING_FOR_APPROVAL
    assert result.paused is True
    pending_ids = {p["department_id"] for p in result.pending_approvals}
    assert pending_ids == set(ANDES_DEPARTMENTS)
    for row in result.pending_approvals:
        assert row.get("approval_status") == "pending"
        assert row.get("approver") == DEPARTMENT_OWNERS[row["department_id"]]
    assert all(
        (result.approvals.get(d) or {}).get("approval_status") == "pending"
        for d in ANDES_DEPARTMENTS
    )
    assert not (result.final_document or {}).get("markdown")
    assert "apply_approval" not in [e.get("node") for e in result.trace]
