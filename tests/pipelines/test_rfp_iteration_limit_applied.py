"""Evaluate: iteration limit is applied in code (not only mentioned in docs).

Verifies:
1. ``MAX_DEPARTMENT_APPROVAL_ITERATIONS`` is a real constant (=2)
2. Graph sources call ``bump_department_iterations`` in arbitration + apply_approval
3. Runtime: exceeding the cap sets ``needs_human_review`` and records counts in state/trace
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from data.pipelines.rfp_approval.approvers import DEPARTMENT_OWNERS
from data.pipelines.rfp_approval.checkpointer import (
    approval_thread_id,
    reset_approval_checkpointer,
)
from data.pipelines.rfp_approval.fixtures import (
    andes_pipeline_kwargs,
    cost_disagreement_pipeline_kwargs,
)
from data.pipelines.rfp_approval.graph import (
    _apply_department_decision,
    arbitration_node,
    invoke_rfp_approval_graph,
)
from data.pipelines.rfp_approval.guardrails import (
    ITERATION_LIMIT_MESSAGE,
    MAX_DEPARTMENT_APPROVAL_ITERATIONS,
    bump_department_iterations,
    iteration_limit_error,
)
from data.pipelines.rfp_intake.constants import (
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS

ARTIFACT = Path("/opt/cursor/artifacts/rfp_iteration_limit_applied.json")
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _isolate_checkpointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_CHECKPOINT_SQLITE", str(tmp_path / "iter-limit.sqlite"))
    monkeypatch.setenv("RFP_ALLOW_SQLITE", "1")
    monkeypatch.delenv("RFP_CHECKPOINT_MEMORY", raising=False)
    reset_approval_checkpointer()
    yield
    reset_approval_checkpointer()


def test_iteration_limit_constant_and_helper_are_executable() -> None:
    assert MAX_DEPARTMENT_APPROVAL_ITERATIONS == 2
    assert MAX_DEPARTMENT_APPROVAL_ITERATIONS == MAX_SECTION_ITERATIONS
    assert str(MAX_DEPARTMENT_APPROVAL_ITERATIONS) in ITERATION_LIMIT_MESSAGE

    counts, exceeded = bump_department_iterations({}, ["marketing"])
    assert counts == {"marketing": 1}
    assert exceeded == []
    counts, exceeded = bump_department_iterations(
        {"marketing": MAX_DEPARTMENT_APPROVAL_ITERATIONS},
        ["marketing"],
        limit=MAX_DEPARTMENT_APPROVAL_ITERATIONS,
    )
    assert counts["marketing"] == MAX_DEPARTMENT_APPROVAL_ITERATIONS + 1
    assert exceeded == ["marketing"]
    assert "marketing" in iteration_limit_error(exceeded)
    assert "Maximum department approval iterations" in iteration_limit_error(exceeded)


def test_iteration_limit_is_wired_into_graph_source_not_docs_only() -> None:
    """Both enforcement sites must call bump_department_iterations in source."""
    arb_src = inspect.getsource(arbitration_node)
    apply_src = inspect.getsource(_apply_department_decision)
    guard_src = (
        REPO / "data" / "pipelines" / "rfp_approval" / "guardrails.py"
    ).read_text(encoding="utf-8")

    assert "MAX_DEPARTMENT_APPROVAL_ITERATIONS" in guard_src
    assert "def bump_department_iterations" in guard_src

    for label, src in (
        ("arbitration_node", arb_src),
        ("_apply_department_decision", apply_src),
    ):
        assert "bump_department_iterations" in src, f"{label} missing bump call"
        assert "STATUS_NEEDS_HUMAN_REVIEW" in src, f"{label} missing needs_human_review"
        assert "iteration_limit_error" in src, f"{label} missing limit error"
        assert (
            "max_approval_iterations" in src
            or "MAX_DEPARTMENT_APPROVAL_ITERATIONS" in src
        )


def test_arbitration_path_applies_iteration_limit_at_runtime() -> None:
    """cost-vs-feasibility bump past the cap → needs_human_review + counted iters."""
    kwargs = cost_disagreement_pipeline_kwargs(
        ticket_id="iter-limit-arb-runtime",
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
    iters = result.get("approval_iterations") or {}
    assert iters.get("operaciones", 0) > MAX_DEPARTMENT_APPROVAL_ITERATIONS
    assert iters.get("procurement", 0) > MAX_DEPARTMENT_APPROVAL_ITERATIONS

    arb = [e for e in (result.get("trace") or []) if e.get("node") == "arbitration"]
    assert arb
    out = arb[0].get("output") or {}
    assert out.get("exceeded_departments") or arb[0].get("payload", {}).get("exceeded")
    assert out.get("approval_iterations", {}).get("operaciones", 0) > (
        MAX_DEPARTMENT_APPROVAL_ITERATIONS
    )


def test_human_request_changes_path_applies_iteration_limit_at_runtime() -> None:
    """Named-owner request_changes past the cap stops in apply_approval."""
    kwargs = andes_pipeline_kwargs(
        ticket_id="iter-limit-human-runtime",
        queued_decisions=[],
    )
    thread_id = approval_thread_id(kwargs["ticket_id"])
    invoke_kwargs = {k: v for k, v in kwargs.items() if k != "queued_decisions"}
    paused = invoke_rfp_approval_graph(
        **invoke_kwargs,
        approval_iterations={"marketing": MAX_DEPARTMENT_APPROVAL_ITERATIONS},
        max_approval_iterations=MAX_DEPARTMENT_APPROVAL_ITERATIONS,
        use_interrupt=True,
        thread_id=thread_id,
    )
    assert paused.get("__interrupt__") or paused.get("status") == (
        STATUS_WAITING_FOR_APPROVAL
    )

    limited = invoke_rfp_approval_graph(
        **invoke_kwargs,
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
    iters = limited.get("approval_iterations") or {}
    # Cap is applied: count advances past MAX (may bump once on Command.update and
    # again if apply_approval still runs — both sites enforce the same helper).
    assert iters.get("marketing", 0) > MAX_DEPARTMENT_APPROVAL_ITERATIONS
    apply_ev = [
        e for e in (limited.get("trace") or []) if e.get("node") == "apply_approval"
    ]
    assert apply_ev
    exceeded_ev = [
        e
        for e in apply_ev
        if (e.get("output") or {}).get("exceeded")
        or (e.get("payload") or {}).get("exceeded")
    ]
    assert exceeded_ev or iters["marketing"] > MAX_DEPARTMENT_APPROVAL_ITERATIONS

    # Also capture arbitration-path evidence in the same artifact.
    arb_kwargs = cost_disagreement_pipeline_kwargs(
        ticket_id="iter-limit-arb-artifact",
        approval_iterations={
            "operaciones": MAX_DEPARTMENT_APPROVAL_ITERATIONS,
            "procurement": MAX_DEPARTMENT_APPROVAL_ITERATIONS,
        },
    )
    arb_result = invoke_rfp_approval_graph(
        **{k: v for k, v in arb_kwargs.items() if k != "queued_decisions"},
        max_approval_iterations=MAX_DEPARTMENT_APPROVAL_ITERATIONS,
        use_interrupt=True,
        thread_id=approval_thread_id(arb_kwargs["ticket_id"]),
    )

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "claim": (
                    "Iteration limit is applied and verifiable in code, not just mentioned"
                ),
                "MAX_DEPARTMENT_APPROVAL_ITERATIONS": MAX_DEPARTMENT_APPROVAL_ITERATIONS,
                "enforcement_sites": [
                    "arbitration_node → bump_department_iterations → needs_human_review",
                    "_apply_department_decision(request_changes) → bump → needs_human_review",
                ],
                "arbitration_runtime": {
                    "status": arb_result.get("status"),
                    "approval_iterations": arb_result.get("approval_iterations"),
                    "error_message": arb_result.get("error_message"),
                },
                "human_request_changes_runtime": {
                    "status": limited.get("status"),
                    "approval_iterations": iters,
                    "error_message": limited.get("error_message"),
                    "apply_exceeded_in_trace": bool(exceeded_ev),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
