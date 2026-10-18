"""Evaluate: generator–evaluator loop, iteration limit, needs_human_review handoff.

CONTEXT §2.3: when the iteration limit is exhausted, keep the last draft +
EvaluationResult and hand off to Part 3 at ``needs_human_review`` (never discard).
CONTEXT §3: average iterations per section target fewer than 2 → cap is 2.
"""

from __future__ import annotations

from pathlib import Path

from data.pipelines.rfp_intake.constants import (
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_intake.context_rules import read_context_company_md
from data.pipelines.rfp_response.agents import DraftResult
from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS
from data.pipelines.rfp_response.evaluators import DimensionResult, EvaluationResult
from data.pipelines.rfp_response.graph import finalize_status_node
from data.pipelines.rfp_response.loop import run_section_loop
from data.pipelines.rfp_response.part3_handoff import build_part3_handoff

REPO = Path(__file__).resolve().parents[2]
LOOP_SRC = REPO / "data" / "pipelines" / "rfp_response" / "loop.py"
GRAPH_SRC = REPO / "data" / "pipelines" / "rfp_response" / "graph.py"


def _fail_eval(department_id: str, msg: str = "Missing brand pillar(s): consistent quality") -> EvaluationResult:
    return EvaluationResult(
        department_id=department_id,
        passed=False,
        readability=DimensionResult("readability", True, 1.0),
        relevance=DimensionResult("relevance", True, 1.0),
        compliance=DimensionResult("compliance", False, 0.2, failures=[msg]),
        feedback=[msg],
        feedback_for_generator=[msg],
    )


def _pass_eval(department_id: str) -> EvaluationResult:
    return EvaluationResult(
        department_id=department_id,
        passed=True,
        readability=DimensionResult("readability", True, 1.0),
        relevance=DimensionResult("relevance", True, 1.0),
        compliance=DimensionResult("compliance", True, 1.0),
        feedback=[],
        feedback_for_generator=[],
    )


def test_context_needs_human_review_is_iteration_exhaustion_handoff() -> None:
    text = read_context_company_md()
    assert "`needs_human_review`" in text
    block = text.split("### 2.3")[1].split("### 2.4")[0]
    assert "needs_human_review" in block
    assert "Iteration limit exhausted" in block
    assert "last draft" in block.casefold() or "EvaluationResult" in block
    assert "Part 3" in block
    kpi = text.split("## 3. Business Metrics")[1].split("## 4.")[0]
    assert "fewer than 2" in kpi.casefold() or "average iterations" in kpi.casefold()
    assert MAX_SECTION_ITERATIONS == 2
    loop_src = LOOP_SRC.read_text(encoding="utf-8")
    assert "MAX_SECTION_ITERATIONS" in loop_src
    assert "STATUS_NEEDS_HUMAN_REVIEW" in loop_src
    assert "feedback_for_generator" in loop_src
    graph_src = GRAPH_SRC.read_text(encoding="utf-8")
    assert "STATUS_NEEDS_HUMAN_REVIEW" in graph_src
    assert "discarded" in graph_src


def test_loop_retries_same_generator_then_stops_at_iteration_limit(monkeypatch) -> None:
    from data.pipelines.rfp_response import loop as loop_mod

    calls: list[dict] = []
    fail_msg = "Missing brand pillar(s): consistent quality"

    def spy_generate(summary, *, feedback=None, feedback_for_generator=None, iteration=1):
        fb = list(feedback_for_generator or feedback or [])
        calls.append(
            {
                "iteration": iteration,
                "agent": "marketing_generator_agent",
                "feedback_for_generator": fb,
            }
        )
        return DraftResult(
            department_id=summary.department_id,
            owner="Camila Ospina",
            draft_content=f"LAST DRAFT iter {iteration} | {' | '.join(fb)}",
            iteration=iteration,
            used_feedback=fb,
            generator_agent="marketing_generator_agent",
        )

    monkeypatch.setattr(loop_mod, "run_generator_agent", spy_generate)
    monkeypatch.setattr(
        loop_mod,
        "evaluate_section",
        lambda **kwargs: _fail_eval(kwargs["department_id"], fail_msg),
    )

    result = run_section_loop(
        department_id="marketing",
        metadata={"client_name": "Synthetic Co", "location": "Bogotá"},
        key_aspects=["Brand terms for Synthetic Co"],
        max_iterations=MAX_SECTION_ITERATIONS,
    )

    assert len(calls) == MAX_SECTION_ITERATIONS == 2
    assert calls[0]["feedback_for_generator"] == []
    assert fail_msg in calls[1]["feedback_for_generator"]
    assert calls[0]["agent"] == calls[1]["agent"] == "marketing_generator_agent"
    assert result.exhausted is True
    assert result.iterations == 2
    assert result.evaluation.passed is False
    assert "LAST DRAFT iter 2" in result.draft_content
    assert result.section_status == STATUS_NEEDS_HUMAN_REVIEW
    assert result.include_in_part3 is True


def test_loop_does_not_run_a_third_iteration_when_capped_at_two(monkeypatch) -> None:
    from data.pipelines.rfp_response import loop as loop_mod

    n = {"count": 0}

    def counting_generate(summary, **kwargs):
        n["count"] += 1
        return DraftResult(
            department_id=summary.department_id,
            owner="Camila Ospina",
            draft_content=f"draft-{n['count']}",
            iteration=n["count"],
            generator_agent="marketing_generator_agent",
        )

    monkeypatch.setattr(loop_mod, "run_generator_agent", counting_generate)
    monkeypatch.setattr(
        loop_mod,
        "evaluate_section",
        lambda **kwargs: _fail_eval(kwargs["department_id"]),
    )
    run_section_loop(
        department_id="marketing",
        metadata={"client_name": "X"},
        key_aspects=["Brand terms"],
        max_iterations=2,
    )
    assert n["count"] == 2


def test_loop_passes_on_second_iteration_after_feedback(monkeypatch) -> None:
    from data.pipelines.rfp_response import loop as loop_mod

    n = {"eval": 0}

    def generate(summary, *, feedback_for_generator=None, iteration=1, **_kwargs):
        return DraftResult(
            department_id=summary.department_id,
            owner="Camila Ospina",
            draft_content=f"draft-{iteration}",
            iteration=iteration,
            used_feedback=list(feedback_for_generator or []),
            generator_agent="operaciones_generator_agent",
        )

    def eval_once_then_pass(**kwargs):
        n["eval"] += 1
        if n["eval"] == 1:
            return _fail_eval(kwargs["department_id"], "Setup/delivery under 10 business days")
        return _pass_eval(kwargs["department_id"])

    monkeypatch.setattr(loop_mod, "run_generator_agent", generate)
    monkeypatch.setattr(loop_mod, "evaluate_section", eval_once_then_pass)
    result = run_section_loop(
        department_id="operaciones",
        metadata={"client_name": "Andes Tech"},
        key_aspects=["Operational feasibility for Andes Tech"],
        max_iterations=2,
    )
    assert n["eval"] == 2
    assert result.exhausted is False
    assert result.iterations == 2
    assert result.evaluation.passed is True
    assert result.section_status != STATUS_NEEDS_HUMAN_REVIEW
    assert result.include_in_part3 is True


def test_exhausted_section_handoff_is_needs_human_review_not_discarded() -> None:
    ev = _fail_eval("training", "Missing certification time")
    section = {
        "department_id": "training",
        "owner": "Jake Morrison",
        "draft_content": "LAST TRAINING DRAFT",
        "evaluation_results": ev.to_dict(),
        "feedback_for_generator": list(ev.feedback_for_generator),
        "iterations": MAX_SECTION_ITERATIONS,
        "exhausted": True,
        "passed": False,
        "section_status": STATUS_NEEDS_HUMAN_REVIEW,
        "include_in_part3": True,
        "generator_agent": "training_generator_agent",
    }
    handoff = build_part3_handoff(
        ticket_id="t-exhausted",
        ticket_status=STATUS_NEEDS_HUMAN_REVIEW,
        section_results=[section],
    )
    assert handoff["discarded"] is False
    assert handoff["next_part"] == 3
    assert handoff["status"] == STATUS_NEEDS_HUMAN_REVIEW
    row = handoff["sections"][0]
    assert row["draft_content"] == "LAST TRAINING DRAFT"
    assert row["evaluation_results"]["passed"] is False
    assert row["status"] == STATUS_NEEDS_HUMAN_REVIEW
    assert row["exhausted"] is True
    assert row["include_in_part3"] is True


def test_finalize_sets_ticket_needs_human_review_when_any_section_exhausted() -> None:
    ev = _fail_eval("procurement")
    state = finalize_status_node(
        {
            "ticket_id": "t-ticket-nhr",
            "all_passed": False,
            "average_iterations": 2.0,
            "section_results": [
                {
                    "department_id": "procurement",
                    "owner": "Lucía Fernández",
                    "draft_content": "LAST PROCUREMENT DRAFT",
                    "evaluation_results": ev.to_dict(),
                    "feedback_for_generator": list(ev.feedback_for_generator),
                    "iterations": 2,
                    "exhausted": True,
                    "passed": False,
                    "section_status": STATUS_NEEDS_HUMAN_REVIEW,
                    "include_in_part3": True,
                    "generator_agent": "procurement_generator_agent",
                }
            ],
            "trace": [],
        }
    )
    assert state["status"] == STATUS_NEEDS_HUMAN_REVIEW
    assert state["discarded"] is False
    assert state["part3_handoff"]["discarded"] is False
    assert state["part3_handoff"]["status"] == STATUS_NEEDS_HUMAN_REVIEW
    assert state["part3_handoff"]["sections"][0]["draft_content"] == "LAST PROCUREMENT DRAFT"
    assert state["trace"][-1]["payload"]["exhausted_any"] is True
    assert state["trace"][-1]["payload"]["discarded"] is False

    passed = finalize_status_node(
        {
            "ticket_id": "t-ok",
            "all_passed": True,
            "section_results": [
                {
                    "department_id": "marketing",
                    "passed": True,
                    "exhausted": False,
                    "section_status": "pending",
                    "draft_content": "ok",
                    "evaluation_results": _pass_eval("marketing").to_dict(),
                    "include_in_part3": True,
                }
            ],
            "trace": [],
        }
    )
    assert passed["status"] == STATUS_WAITING_FOR_APPROVAL
    assert passed["discarded"] is False
