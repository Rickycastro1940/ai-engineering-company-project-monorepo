"""Part 3 guardrails: iteration cap, fixed arbitration node, per-node trace."""

from __future__ import annotations

from pathlib import Path

import pytest

from data.pipelines.rfp_approval.checkpointer import reset_approval_checkpointer
from data.pipelines.rfp_approval.graph import (
    NODE_AGENTS,
    arbitration_node,
    invoke_rfp_approval_graph,
)
from data.pipelines.rfp_approval.guardrails import (
    MAX_DEPARTMENT_APPROVAL_ITERATIONS,
    bump_department_iterations,
    iteration_limit_error,
    trace_has_required_fields,
)
from data.pipelines.rfp_intake.constants import (
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "guardrails.sqlite"))
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


ANDES_SECTIONS = [
    {
        "department_id": "marketing",
        "draft_content": "## Brand terms\nOffer validity period: 30 days from issuance.\n",
    },
    {
        "department_id": "operaciones",
        "draft_content": "## Setup times\nSetup in 12 business days.\n## Cost per event\nUSD $20.\n",
    },
    {
        "department_id": "procurement",
        "draft_content": "## Estimated ingredient cost based on volume\nUSD $80.\n",
    },
]


def test_max_department_approval_iterations_matches_part2_section_cap() -> None:
    assert MAX_DEPARTMENT_APPROVAL_ITERATIONS == 2
    assert MAX_SECTION_ITERATIONS == 2
    assert MAX_DEPARTMENT_APPROVAL_ITERATIONS == MAX_SECTION_ITERATIONS


def test_bump_department_iterations_enforces_limit() -> None:
    counts, exceeded = bump_department_iterations({}, ["operaciones", "procurement"])
    assert counts == {"operaciones": 1, "procurement": 1}
    assert exceeded == []
    counts, exceeded = bump_department_iterations(
        counts, ["operaciones"], limit=MAX_DEPARTMENT_APPROVAL_ITERATIONS
    )
    assert counts["operaciones"] == 2
    assert exceeded == []
    counts, exceeded = bump_department_iterations(
        counts, ["operaciones"], limit=MAX_DEPARTMENT_APPROVAL_ITERATIONS
    )
    assert counts["operaciones"] == 3
    assert exceeded == ["operaciones"]
    assert "operaciones" in iteration_limit_error(exceeded)


def test_arbitration_is_dedicated_fixed_arbiter_node_not_llm() -> None:
    src = Path(__file__).resolve().parents[2] / "data/pipelines/rfp_approval/arbitration.py"
    text = src.read_text(encoding="utf-8")
    assert "CONTEXT §7" in text or "CONTEXT" in text
    assert "not an llm" in text.casefold() or "not llm" in text.casefold()
    for banned in ("openai", "ChatOpenAI", "invoke_llm", "llm.invoke"):
        assert banned not in text
    assert NODE_AGENTS["arbitration"] == "fixed_arbitration"
    assert callable(arbitration_node)


def test_arbitration_stops_when_department_loop_exceeds_max() -> None:
    """cost-vs-feasibility forces request_changes; repeating past the cap stops the loop."""
    kwargs = dict(
        ticket_id="guard-iter-limit",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=ANDES_SECTIONS,
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing", "operaciones", "procurement"],
        requires_ceo_approval=False,
        use_interrupt=True,
        # Already used the full budget once; this arbitration bump exceeds.
        approval_iterations={"operaciones": 2, "procurement": 2},
        max_approval_iterations=MAX_DEPARTMENT_APPROVAL_ITERATIONS,
        thread_id="guard-iter-limit-thread",
    )
    result = invoke_rfp_approval_graph(**kwargs)
    assert result.get("status") == STATUS_NEEDS_HUMAN_REVIEW
    assert result.get("error_message")
    assert "Maximum department approval iterations" in str(result.get("error_message"))
    assert (result.get("approvals") or {}).get("operaciones", {}).get(
        "approval_status"
    ) == "request_changes"
    assert not result.get("__interrupt__")
    arb = [e for e in (result.get("trace") or []) if e.get("node") == "arbitration"]
    assert arb
    assert arb[0].get("agent") == "fixed_arbitration"
    assert arb[0].get("output", {}).get("llm_resolved") is False


def test_every_node_trace_logs_agent_input_output_timestamp() -> None:
    result = invoke_rfp_approval_graph(
        ticket_id="guard-trace",
        status=STATUS_WAITING_FOR_APPROVAL,
        sections=[
            {
                "department_id": "marketing",
                "draft_content": "## Brand terms\nOffer validity period: 30 days from issuance.\n",
            }
        ],
        metadata={"client_name": "Andes Tech Solutions"},
        departments_needed=["marketing"],
        requires_ceo_approval=False,
        use_interrupt=True,
        thread_id="guard-trace-thread",
    )
    trace = list(result.get("trace") or [])
    assert trace, "expected node trace events"
    for event in trace:
        assert trace_has_required_fields(event), event
        assert event["agent"]
        assert event["timestamp"]
        assert "T" in str(event["timestamp"])
    nodes = {e["node"] for e in trace}
    assert "load_handoff" in nodes
    assert "surface_conflicts" in nodes
    assert "arbitration" in nodes
    arbitration = next(e for e in trace if e["node"] == "arbitration")
    assert arbitration["agent"] == "fixed_arbitration"
    assert arbitration["input"]["mode"] == "fixed_arbiter_table"
    assert arbitration["output"]["llm_resolved"] is False
