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


def test_collect_approvals_interrupts_then_enters_apply_approval() -> None:
    import inspect

    from data.pipelines.rfp_approval.graph import (
        APPLY_APPROVAL_NODE,
        apply_approval_node,
        collect_approvals_node,
        resume_command,
    )

    collect_src = inspect.getsource(collect_approvals_node)
    apply_src = inspect.getsource(apply_approval_node)
    resume_src = inspect.getsource(resume_command)
    invoke_src = inspect.getsource(invoke_rfp_approval_graph)

    assert "_interrupt(" in collect_src
    assert "_goto_apply_approval" in collect_src
    assert collect_src.index("_interrupt(") < collect_src.index("_goto_apply_approval")
    assert "_apply_department_decision" not in collect_src
    assert 'status != "pending"' in collect_src
    assert collect_src.index('status != "pending"') < collect_src.index("_interrupt(")

    assert "_apply_department_decision" in apply_src
    assert "_apply_ceo_decision" in apply_src
    assert APPLY_APPROVAL_NODE in apply_src or "apply_approval" in apply_src

    assert "goto=APPLY_APPROVAL_NODE" in resume_src
    assert "_applied_resume_update" in resume_src or "_apply_department_decision" in resume_src
    assert "prepare_resume(" in invoke_src
    assert "resume_command(" in invoke_src
    assert "graph.invoke(initial" in invoke_src
    assert invoke_src.index("prepare_resume(") < invoke_src.index("resume_command(")
    assert invoke_src.index("resume_command(") < invoke_src.index("graph.invoke(initial")


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


def test_second_department_resume_persists_after_first_send_branch() -> None:
    """Marketing-first (Send order) then operaciones must both land, approve or reject."""
    kwargs = dict(
        ticket_id="hitl-second-resume",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=ANDES_SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing", "operaciones", "procurement"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-second-resume-thread",
    )
    paused = invoke_rfp_approval_graph(**kwargs)
    assert _interrupt_department_ids(paused) == {
        "marketing",
        "operaciones",
        "procurement",
    }
    after_mkt = invoke_rfp_approval_graph(
        **kwargs,
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    assert (after_mkt.get("approvals") or {}).get("marketing", {}).get(
        "approval_status"
    ) == "approved"
    remaining = _interrupt_department_ids(after_mkt)
    assert "marketing" not in remaining
    assert remaining == {"operaciones", "procurement"}

    after_ops = invoke_rfp_approval_graph(
        **kwargs,
        resume={
            "department_id": "operaciones",
            "decision": "rejected",
            "approver": "Felipe Guerrero",
        },
    )
    approvals = after_ops.get("approvals") or {}
    assert approvals.get("marketing", {}).get("approval_status") == "approved"
    assert approvals.get("operaciones", {}).get("approval_status") == "rejected"
    remaining = _interrupt_department_ids(after_ops)
    assert "operaciones" not in remaining
    assert remaining == {"procurement"}
    assert after_ops.get("status") != "done"


def _trace_nodes(result: dict) -> list[str]:
    return [str(event.get("node") or "") for event in (result.get("trace") or [])]


def test_resume_enters_apply_approval_without_restarting_load_handoff() -> None:
    kwargs = dict(
        ticket_id="hitl-resume-entry",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-resume-entry-thread",
    )
    paused = invoke_rfp_approval_graph(**kwargs)
    assert paused.get("__interrupt__")
    assert _trace_nodes(paused).count("load_handoff") == 1
    assert "apply_approval" not in _trace_nodes(paused)

    resumed = invoke_rfp_approval_graph(
        **kwargs,
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    nodes = _trace_nodes(resumed)
    assert nodes.count("load_handoff") == 1
    assert nodes.count("arbitration") == 1
    assert "apply_approval" in nodes
    apply_at = nodes.index("apply_approval")
    assert "load_handoff" not in nodes[apply_at:]
    assert resumed.get("status") == "done"


def test_resume_without_pause_does_not_restart_the_flow() -> None:
    result = invoke_rfp_approval_graph(
        ticket_id="hitl-resume-not-paused",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-resume-not-paused-thread",
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": "Camila Ospina",
        },
    )
    assert result.get("error_message") == "approval_not_paused"
    assert result.get("status") != "done"
    assert not result.get("final_document")
    assert _trace_nodes(result).count("load_handoff") == 0


def test_invalid_resume_decision_does_not_enter_the_graph() -> None:
    kwargs = dict(
        ticket_id="hitl-invalid-resume",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-invalid-resume-thread",
    )
    paused = invoke_rfp_approval_graph(**kwargs)
    assert paused.get("__interrupt__")

    rejected = invoke_rfp_approval_graph(
        **kwargs,
        resume={
            "department_id": "marketing",
            "decision": "maybe",
            "approver": "Camila Ospina",
        },
    )
    assert rejected.get("error_message")
    assert "approve" in str(rejected.get("error_message") or "").casefold()
    assert rejected.get("paused") is True
    assert "apply_approval" not in _trace_nodes(rejected)
    assert (rejected.get("approvals") or {}).get("marketing", {}).get(
        "approval_status"
    ) != "approved"

    done = invoke_rfp_approval_graph(
        **kwargs,
        resume={
            "department_id": "marketing",
            "decision": "approve",
            "approver": "Camila Ospina",
        },
    )
    assert done.get("status") == "done"
    assert done.get("approvals", {}).get("marketing", {}).get("approval_status") == "approved"


def test_resume_reject_and_request_changes_are_valid_human_responses() -> None:
    reject_kwargs = dict(
        ticket_id="hitl-reject",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-reject-thread",
    )
    invoke_rfp_approval_graph(**reject_kwargs)
    rejected = invoke_rfp_approval_graph(
        **reject_kwargs,
        resume={
            "department_id": "marketing",
            "decision": "reject",
            "approver": "Camila Ospina",
        },
    )
    assert rejected.get("status") != "done"
    assert rejected.get("approvals", {}).get("marketing", {}).get("approval_status") == "rejected"
    assert not (rejected.get("final_document") or {}).get("markdown")

    change_kwargs = dict(
        ticket_id="hitl-request-changes",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="hitl-request-changes-thread",
    )
    invoke_rfp_approval_graph(**change_kwargs)
    changed = invoke_rfp_approval_graph(
        **change_kwargs,
        resume={
            "department_id": "marketing",
            "decision": "request changes",
            "approver": "Camila Ospina",
        },
    )
    assert changed.get("status") != "done"
    assert changed.get("approvals", {}).get("marketing", {}).get("approval_status") == "request_changes"
    assert not (changed.get("final_document") or {}).get("markdown")
