"""Part 3 HITL: LangGraph interrupt pauses for named-owner resume."""

from __future__ import annotations

from data.pipelines.rfp_approval.graph import invoke_rfp_approval_graph
from data.pipelines.rfp_intake.constants import STATUS_WAITING_FOR_APPROVAL

SECTIONS = [
    {
        "department_id": "marketing",
        "draft_content": "## Brand terms\nOffer validity period: 30 days from issuance.\n",
    }
]


def test_interrupt_pauses_then_resume_with_camila_approval() -> None:
    kwargs = dict(
        ticket_id="hitl-marketing",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-marketing-thread",
    )
    paused = invoke_rfp_approval_graph(**kwargs)
    interrupts = paused.get("__interrupt__") or []
    assert interrupts, f"expected interrupt payload, got keys={list(paused)}"
    value = getattr(interrupts[0], "value", None) or interrupts[0]
    if isinstance(value, dict):
        pending = value.get("pending") or []
        assert any(p.get("approver") == "Camila Ospina" for p in pending)

    resumed = invoke_rfp_approval_graph(
        **kwargs,
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    assert resumed.get("status") == "done"
    assert (resumed.get("final_document") or {}).get("ticket_id") == "hitl-marketing"
    assert resumed.get("approvals", {}).get("marketing", {}).get("approval_status") == "approved"
