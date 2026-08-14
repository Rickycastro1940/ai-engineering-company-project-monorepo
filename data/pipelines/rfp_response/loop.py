"""Generator → evaluator iteration loop per department (CONTEXT §3 KPI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS
from data.pipelines.rfp_response.evaluators import EvaluationResult, evaluate_section
from data.pipelines.rfp_response.agents import (
    DraftResult,
    Part1DepartmentSummary,
    get_generator_agent,
    run_generator_agent,
)


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "department_id": self.department_id,
            "owner": self.owner,
            "draft_content": self.draft_content,
            "evaluation_results": self.evaluation.to_dict(),
            "iterations": self.iterations,
            "exhausted": self.exhausted,
            "passed": self.evaluation.passed,
            "generator_agent": self.generator_agent,
            "kb_grounded": self.kb_grounded,
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
    """Draft → evaluate → revise until pass or iteration limit.

    Prefers a ``Part1DepartmentSummary`` (per-department Part 1 handoff). The
    department's generator agent is the only writer of ``draft_content``.
    """
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
    feedback: list[str] = []
    history: list[dict[str, Any]] = []
    draft: DraftResult | None = None
    evaluation: EvaluationResult | None = None

    limit = max(1, int(max_iterations))
    for iteration in range(1, limit + 1):
        draft = run_generator_agent(
            summary, feedback=feedback, iteration=iteration
        )
        evaluation = evaluate_section(
            department_id=summary.department_id,
            draft_content=draft.draft_content,
            key_aspects=list(summary.key_aspects),
            metadata=dict(summary.metadata),
        )
        history.append(
            {
                "iteration": iteration,
                "generator_agent": agent.agent_name,
                "part1_summary_used": draft.part1_summary_used,
                "kb_grounded": draft.kb_grounded,
                "kb_sources": list(draft.kb_sources),
                "passed": evaluation.passed,
                "evaluators_parallel": evaluation.parallel,
                "evaluator_agents": list(evaluation.evaluator_agents),
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
            )
        feedback = list(evaluation.feedback)

    assert draft is not None and evaluation is not None
    return SectionLoopResult(
        department_id=summary.department_id,
        owner=draft.owner,
        draft_content=draft.draft_content,
        evaluation=evaluation,
        iterations=limit,
        exhausted=True,
        history=history,
        generator_agent=agent.agent_name,
        kb_grounded=draft.kb_grounded,
    )
