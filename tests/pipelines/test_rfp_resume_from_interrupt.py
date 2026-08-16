"""Evaluate: resume continues from interrupt() — never restarts from START / load_handoff."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.fixtures import (
    ANDES_DEPARTMENTS,
    andes_pipeline_kwargs,
)
from data.pipelines.rfp_approval.graph import (
    get_compiled_rfp_approval_graph,
    graph_is_paused,
    interrupt_payloads,
    invoke_rfp_approval_graph,
)
from data.pipelines.rfp_intake.constants import STATUS_WAITING_FOR_APPROVAL

ARTIFACT = Path("/opt/cursor/artifacts/rfp_resume_from_interrupt_point.json")


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "resume-eval.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def _nodes(result: dict) -> list[str]:
    return [str(e.get("node") or "") for e in (result.get("trace") or [])]


def _counts(nodes: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for n in nodes:
        out[n] = out.get(n, 0) + 1
    return out


def test_execution_resumes_from_interrupt_without_restarting_flow() -> None:
    """Pause → resume one department: same checkpoint, no second load_handoff."""
    kwargs = andes_pipeline_kwargs(
        ticket_id="resume-from-interrupt",
        queued_decisions=[],
    )
    thread_id = approval_thread_id(kwargs["ticket_id"])
    invoke_kwargs = {k: v for k, v in kwargs.items() if k != "queued_decisions"}
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_compiled_rfp_approval_graph(use_interrupt=True)

    paused = invoke_rfp_approval_graph(
        **invoke_kwargs,
        use_interrupt=True,
        thread_id=thread_id,
    )
    assert interrupt_payloads(paused), "expected HITL pause"
    paused_nodes = _nodes(paused)
    paused_counts = _counts(paused_nodes)
    assert paused_counts.get("load_handoff") == 1
    assert paused_counts.get("surface_conflicts") == 1
    assert paused_counts.get("arbitration") == 1
    assert "apply_approval" not in paused_nodes
    assert "synthesizer" not in paused_nodes
    assert graph_is_paused(graph.get_state(config))

    # Resume operaciones (not the first Send order) from the interruption point.
    resumed = invoke_rfp_approval_graph(
        **invoke_kwargs,
        use_interrupt=True,
        thread_id=thread_id,
        resume={
            "department_id": "operaciones",
            "decision": "approved",
            "approver": DEPARTMENT_OWNERS["operaciones"],
        },
    )
    resumed_nodes = _nodes(resumed)
    resumed_counts = _counts(resumed_nodes)

    # Entire flow was NOT restarted: handoff / conflict / arbitration stay at 1.
    assert resumed_counts.get("load_handoff") == 1
    assert resumed_counts.get("surface_conflicts") == 1
    assert resumed_counts.get("arbitration") == 1
    assert "apply_approval" in resumed_nodes
    apply_at = resumed_nodes.index("apply_approval")
    # Nothing after the interrupt re-enters the front of the graph.
    assert "load_handoff" not in resumed_nodes[apply_at:]
    assert "surface_conflicts" not in resumed_nodes[apply_at:]
    assert "arbitration" not in resumed_nodes[apply_at:]

    assert (resumed.get("approvals") or {}).get("operaciones", {}).get(
        "approval_status"
    ) == "approved"
    # Sibling branches still at their interruption points.
    still = {
        str(p.get("department_id"))
        for p in interrupt_payloads(resumed)
        if p.get("department_id")
    }
    assert "marketing" in still
    assert "procurement" in still
    assert "operaciones" not in still
    assert resumed.get("status") == STATUS_WAITING_FOR_APPROVAL
    assert graph_is_paused(graph.get_state(config))

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "Execution resumes from the interruption point without "
                    "restarting the entire flow"
                ),
                "thread_id": thread_id,
                "paused": {
                    "node_counts": paused_counts,
                    "interrupted": sorted(
                        p.get("department_id")
                        for p in interrupt_payloads(paused)
                        if p.get("department_id")
                    ),
                },
                "after_resume_operaciones": {
                    "node_counts": resumed_counts,
                    "apply_approval_index": apply_at,
                    "nodes_after_apply": resumed_nodes[apply_at:],
                    "operaciones_status": (resumed.get("approvals") or {})
                    .get("operaciones", {})
                    .get("approval_status"),
                    "still_interrupted": sorted(still),
                    "status": resumed.get("status"),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_resume_without_existing_pause_does_not_restart_from_start() -> None:
    """Resume on a cold thread returns approval_not_paused — no load_handoff."""
    result = invoke_rfp_approval_graph(
        ticket_id="resume-cold",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=andes_pipeline_kwargs()["sections"][:1],
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id=approval_thread_id("resume-cold"),
        resume={
            "department_id": "marketing",
            "decision": "approved",
            "approver": DEPARTMENT_OWNERS["marketing"],
        },
    )
    assert result.get("error_message") == "approval_not_paused"
    assert _counts(_nodes(result)).get("load_handoff", 0) == 0
    assert result.get("status") != "done"


def test_source_resume_command_targets_apply_approval_not_start() -> None:
    import inspect

    from data.pipelines.rfp_approval.graph import (
        resume_command,
        invoke_rfp_approval_graph,
    )

    resume_src = inspect.getsource(resume_command)
    invoke_src = inspect.getsource(invoke_rfp_approval_graph)
    assert "never START" in resume_src or "goto=APPLY_APPROVAL_NODE" in resume_src
    assert "Command(resume=" in resume_src
    assert "goto=APPLY_APPROVAL_NODE" in resume_src
    assert invoke_src.index("resume_command(") < invoke_src.index(
        "graph.invoke(initial"
    )
    assert "prepare_resume(" in invoke_src
