"""Generator–evaluator loop: feedback_for_generator, iteration cap, Part 3 handoff."""

from __future__ import annotations

from data.pipelines.rfp_intake.constants import (
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS
from data.pipelines.rfp_response.evaluators import DimensionResult, EvaluationResult
from data.pipelines.rfp_response.loop import run_section_loop
from data.pipelines.rfp_response.part3_handoff import build_part3_handoff


def test_failed_eval_returns_to_same_generator_with_feedback_for_generator(
    monkeypatch,
) -> None:
    from data.pipelines.rfp_response import loop as loop_mod

    calls: list[dict] = []

    def spy_generate(summary, *, feedback=None, feedback_for_generator=None, iteration=1):
        from data.pipelines.rfp_response.agents import DraftResult, get_generator_agent

        fb = list(feedback_for_generator or feedback or [])
        calls.append(
            {
                "iteration": iteration,
                "department_id": summary.department_id,
                "agent": get_generator_agent(summary.department_id).agent_name,
                "feedback_for_generator": fb,
            }
        )
        return DraftResult(
            department_id=summary.department_id,
            owner="Camila Ospina",
            draft_content=f"# marketing draft iter {iteration}\n" + " ".join(fb),
            iteration=iteration,
            used_feedback=fb,
            generator_agent="marketing_generator_agent",
        )

    def always_fail(**kwargs):
        msg = "Missing brand pillar(s): consistent quality"
        return EvaluationResult(
            department_id=kwargs["department_id"],
            passed=False,
            readability=DimensionResult("readability", True, 1.0),
            relevance=DimensionResult("relevance", True, 1.0),
            compliance=DimensionResult("compliance", False, 0.2, failures=[msg]),
            feedback=[msg],
            feedback_for_generator=[msg],
        )

    monkeypatch.setattr(loop_mod, "run_generator_agent", spy_generate)
    monkeypatch.setattr(loop_mod, "evaluate_section", always_fail)

    result = run_section_loop(
        department_id="marketing",
        metadata={"client_name": "X", "location": "Y"},
        key_aspects=["Brand terms for X"],
        max_iterations=MAX_SECTION_ITERATIONS,
    )
    assert MAX_SECTION_ITERATIONS == 2
    assert len(calls) == MAX_SECTION_ITERATIONS
    assert calls[0]["feedback_for_generator"] == []
    assert calls[1]["feedback_for_generator"] == [
        "Missing brand pillar(s): consistent quality"
    ]
    assert calls[0]["agent"] == calls[1]["agent"] == "marketing_generator_agent"
    assert result.exhausted is True
    assert result.iterations == 2
    assert result.draft_content  # last draft kept
    assert result.evaluation.passed is False  # last EvaluationResult kept
    assert result.section_status == STATUS_NEEDS_HUMAN_REVIEW
    assert result.include_in_part3 is True


def test_iteration_limit_never_runs_forever(monkeypatch) -> None:
    from data.pipelines.rfp_response import loop as loop_mod

    n = {"count": 0}

    def counting_generate(summary, **kwargs):
        from data.pipelines.rfp_response.agents import DraftResult

        n["count"] += 1
        return DraftResult(
            department_id=summary.department_id,
            owner="x",
            draft_content="draft",
            iteration=n["count"],
        )

    def fail(**kwargs):
        return EvaluationResult(
            department_id=kwargs["department_id"],
            passed=False,
            readability=DimensionResult("readability", False, 0.0, failures=["short"]),
            relevance=DimensionResult("relevance", True, 1.0),
            compliance=DimensionResult("compliance", True, 1.0),
            feedback=["short"],
            feedback_for_generator=["short"],
        )

    monkeypatch.setattr(loop_mod, "run_generator_agent", counting_generate)
    monkeypatch.setattr(loop_mod, "evaluate_section", fail)
    run_section_loop(
        department_id="marketing",
        metadata={"client_name": "X"},
        key_aspects=["Brand terms"],
        max_iterations=2,
    )
    assert n["count"] == 2


def test_part3_handoff_includes_exhausted_section_and_does_not_discard() -> None:
    ev = EvaluationResult(
        department_id="marketing",
        passed=False,
        readability=DimensionResult("readability", True, 1.0),
        relevance=DimensionResult("relevance", True, 1.0),
        compliance=DimensionResult("compliance", False, 0.2, failures=["x"]),
        feedback=["x"],
        feedback_for_generator=["x"],
    )
    section = {
        "department_id": "marketing",
        "owner": "Camila Ospina",
        "draft_content": "LAST DRAFT",
        "evaluation_results": ev.to_dict(),
        "feedback_for_generator": ["x"],
        "iterations": 2,
        "exhausted": True,
        "passed": False,
        "section_status": STATUS_NEEDS_HUMAN_REVIEW,
        "include_in_part3": True,
        "generator_agent": "marketing_generator_agent",
    }
    handoff = build_part3_handoff(
        ticket_id="t-loop",
        ticket_status=STATUS_NEEDS_HUMAN_REVIEW,
        section_results=[section],
    )
    assert handoff["discarded"] is False
    assert handoff["next_part"] == 3
    assert handoff["status"] == STATUS_NEEDS_HUMAN_REVIEW
    assert len(handoff["sections"]) == 1
    row = handoff["sections"][0]
    assert row["draft_content"] == "LAST DRAFT"
    assert row["evaluation_results"]["passed"] is False
    assert row["feedback_for_generator"] == ["x"]
    assert row["status"] == STATUS_NEEDS_HUMAN_REVIEW
    assert row["include_in_part3"] is True


def test_passing_loop_is_pending_for_part3(monkeypatch) -> None:
    from data.pipelines.rfp_response import loop as loop_mod
    from data.pipelines.rfp_response.agents import DraftResult

    def ok_generate(summary, **kwargs):
        return DraftResult(
            department_id=summary.department_id,
            owner="Camila Ospina",
            draft_content="# ok",
            generator_agent="marketing_generator_agent",
        )

    def pass_eval(**kwargs):
        return EvaluationResult(
            department_id=kwargs["department_id"],
            passed=True,
            readability=DimensionResult("readability", True, 1.0),
            relevance=DimensionResult("relevance", True, 1.0),
            compliance=DimensionResult("compliance", True, 1.0),
            feedback=[],
            feedback_for_generator=[],
        )

    monkeypatch.setattr(loop_mod, "run_generator_agent", ok_generate)
    monkeypatch.setattr(loop_mod, "evaluate_section", pass_eval)
    result = run_section_loop(
        department_id="marketing",
        metadata={"client_name": "X"},
        key_aspects=["Brand terms"],
        max_iterations=2,
    )
    assert result.exhausted is False
    assert result.iterations == 1
    assert result.section_status == "pending"
    handoff = build_part3_handoff(
        ticket_id="t-ok",
        ticket_status=STATUS_WAITING_FOR_APPROVAL,
        section_results=[result.to_dict()],
    )
    assert handoff["discarded"] is False
    assert handoff["sections"][0]["include_in_part3"] is True
