"""Part 3 HITL: LangGraph interrupt pauses for named-owner resume."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_approval.checkpointer import reset_approval_checkpointer
from data.pipelines.rfp_approval.graph import invoke_rfp_approval_graph
from data.pipelines.rfp_intake.constants import STATUS_WAITING_FOR_APPROVAL


@pytest.fixture(autouse=True)
def _isolate_hitl_checkpointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "hitl.sqlite"))
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()

SECTIONS = [
    {
        "department_id": "marketing",
        "draft_content": "## Brand terms\nOffer validity period: 30 days from issuance.\n",
    }
]

ANDES_SECTIONS = [
    {
        "department_id": "marketing",
        "draft_content": "## Brand terms\nOffer validity period: 30 days from issuance.\n",
    },
    {
        "department_id": "operaciones",
        "draft_content": "## Setup times\nSetup in 12 business days.\n",
    },
    {
        "department_id": "procurement",
        "draft_content": "## Estimated ingredient cost based on volume\nUSD $20.\n",
    },
]


def _interrupt_department_ids(result: dict) -> set[str]:
    ids: set[str] = set()
    for item in result.get("__interrupt__") or []:
        value = getattr(item, "value", None)
        if value is None:
            value = item
        if isinstance(value, dict) and value.get("department_id"):
            ids.add(str(value["department_id"]))
    return ids


def test_collect_approvals_interrupts_before_apply_decision() -> None:
    import inspect

    from data.pipelines.rfp_approval.graph import collect_approvals_node

    src = inspect.getsource(collect_approvals_node)
    assert "_interrupt(" in src
    assert src.index("_interrupt(") < src.index("_apply_department_decision")
    assert 'status != "pending"' in src
    assert src.index('status != "pending"') < src.index("_interrupt(")


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
    marketing = (paused.get("approvals") or {}).get("marketing") or {}
    assert marketing.get("approval_status") != "approved"
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


def test_department_interrupt_is_per_branch_and_skips_already_done() -> None:
    """Pending departments interrupt in parallel; a done branch is not paused again."""
    kwargs = dict(
        ticket_id="hitl-parallel",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=ANDES_SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing", "operaciones", "procurement"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-parallel-thread",
    )
    paused = invoke_rfp_approval_graph(**kwargs)
    assert _interrupt_department_ids(paused) == {
        "marketing",
        "operaciones",
        "procurement",
    }
    for dept in ("marketing", "operaciones", "procurement"):
        assert (paused.get("approvals") or {}).get(dept, {}).get(
            "approval_status"
        ) != "approved"

    after_ops = invoke_rfp_approval_graph(
        **kwargs,
        resume={
            "department_id": "operaciones",
            "decision": "approved",
            "approver": "Felipe Guerrero",
        },
    )
    assert (
        after_ops.get("approvals") or {}
    ).get("operaciones", {}).get("approval_status") == "approved"
    assert (
        after_ops.get("approvals") or {}
    ).get("marketing", {}).get("approval_status") != "approved"
    remaining = _interrupt_department_ids(after_ops)
    assert "operaciones" not in remaining
    assert remaining == {"marketing", "procurement"}
    assert after_ops.get("status") != "done"
