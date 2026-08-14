"""Generator → evaluator iteration loop per department (CONTEXT §3 KPI).

If a section fails evaluation it returns to **that department's** generator
agent with ``EvaluationResult.feedback_for_generator``. The loop is capped at
``MAX_SECTION_ITERATIONS`` (default 2). Exhaustion keeps the last draft +
EvaluationResult, marks ``needs_human_review``, and still includes the
section in the Part 3 handoff (ticket is never discarded).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_intake.constants import STATUS_NEEDS_HUMAN_REVIEW
from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS
from data.pipelines.rfp_response.evaluators import EvaluationResult, evaluate_section
from data.pipelines.rfp_response.agents import (
    DraftResult,
    Part1DepartmentSummary,
    get_generator_agent,
    run_generator_agent,
)
from data.pipelines.rfp_response.part3_handoff import section_status_for_loop


@dataclass
class SectionLoopResult:
    department_id: str
    owner: str
    draft_content: str
    evaluation: EvaluationResult
    iterations: int
    exhausted: bool
    history: list[dict[str, Any]] = field(default_factory=list)
    generator_agent: str = ""
    kb_grounded: bool = False
    section_status: str = "pending"
    include_in_part3: bool = True

    def to_dict(self) -> dict[str, Any]:
        ev = self.evaluation.to_dict()
        return {
            "department_id": self.department_id,
            "owner": self.owner,
            "draft_content": self.draft_content,
            "evaluation_results": ev,
            "feedback_for_generator": list(
                self.evaluation.feedback_for_generator or self.evaluation.feedback
            ),
            "iterations": self.iterations,
            "exhausted": self.exhausted,
            "passed": self.evaluation.passed,
            "generator_agent": self.generator_agent,
            "kb_grounded": self.kb_grounded,
            "section_status": self.section_status,
            "include_in_part3": True,
            "history": list(self.history),
        }


def run_section_loop(
    *,
    department_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    key_aspects: list[str] | None = None,
    open_questions: list[str] | None = None,
    max_iterations: int = MAX_SECTION_ITERATIONS,
    summary: Part1DepartmentSummary | None = None,
    ticket_id: str | None = None,
) -> SectionLoopResult:
    """Draft → evaluate → revise until pass or iteration limit."""
    if summary is None:
        if not department_id:
            raise ValueError("run_section_loop requires department_id or summary")
        summary = Part1DepartmentSummary.from_work_stream(
            {
                "department_id": department_id,
                "key_aspects": list(key_aspects or []),
                "open_questions": list(open_questions or []),
            },
            metadata=dict(metadata or {}),
            ticket_id=ticket_id,
        )
    agent = get_generator_agent(summary.department_id)
    feedback_for_generator: list[str] = []
    history: list[dict[str, Any]] = []
    draft: DraftResult | None = None
    evaluation: EvaluationResult | None = None

    limit = max(1, int(max_iterations))

    for iteration in range(1, limit + 1):
        # Always the corresponding department generator — never a different agent
        draft = run_generator_agent(
            summary,
            feedback_for_generator=feedback_for_generator or None,
            iteration=iteration,
        )
        evaluation = evaluate_section(
            department_id=summary.department_id,
            draft_content=draft.draft_content,
            key_aspects=list(summary.key_aspects),
            metadata=dict(summary.metadata),
        )
        fb = list(evaluation.feedback_for_generator or evaluation.feedback)
        history.append(
            {
                "iteration": iteration,
                "generator_agent": agent.agent_name,
                "returned_to_generator": agent.agent_name if not evaluation.passed else None,
                "part1_summary_used": draft.part1_summary_used,
                "kb_grounded": draft.kb_grounded,
                "kb_sources": list(draft.kb_sources),
                "passed": evaluation.passed,
                "evaluators_parallel": evaluation.parallel,
                "evaluator_agents": list(evaluation.evaluator_agents),
                "feedback_for_generator": fb,
                "feedback": list(evaluation.feedback),
                "scores": {
                    "readability": evaluation.readability.score,
                    "relevance": evaluation.relevance.score,
                    "compliance": evaluation.compliance.score,
                },
            }
        )
        if evaluation.passed:
            return SectionLoopResult(
                department_id=summary.department_id,
                owner=draft.owner,
                draft_content=draft.draft_content,
                evaluation=evaluation,
                iterations=iteration,
                exhausted=False,
                history=history,
                generator_agent=agent.agent_name,
                kb_grounded=draft.kb_grounded,
                section_status=section_status_for_loop(passed=True, exhausted=False),
                include_in_part3=True,
            )
        # Fail → return to the same generator with EvaluationResult.feedback_for_generator
        feedback_for_generator = fb

    assert draft is not None and evaluation is not None
    return SectionLoopResult(
        department_id=summary.department_id,
        owner=draft.owner,
        draft_content=draft.draft_content,  # last draft kept
        evaluation=evaluation,  # last EvaluationResult kept
        iterations=limit,
        exhausted=True,
        history=history,
        generator_agent=agent.agent_name,
        kb_grounded=draft.kb_grounded,
        section_status=STATUS_NEEDS_HUMAN_REVIEW,
        include_in_part3=True,
    )
