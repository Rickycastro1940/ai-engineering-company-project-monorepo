"""Generator → evaluator iteration loop per department (CONTEXT §3 KPI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS
from data.pipelines.rfp_response.evaluators import EvaluationResult, evaluate_section
from data.pipelines.rfp_response.generator import DraftResult, generate_department_draft


@dataclass
class SectionLoopResult:
    department_id: str
    owner: str
    draft_content: str
    evaluation: EvaluationResult
    iterations: int
    exhausted: bool
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "department_id": self.department_id,
            "owner": self.owner,
            "draft_content": self.draft_content,
            "evaluation_results": self.evaluation.to_dict(),
            "iterations": self.iterations,
            "exhausted": self.exhausted,
            "passed": self.evaluation.passed,
            "history": list(self.history),
        }


def run_section_loop(
    *,
    department_id: str,
    metadata: dict[str, Any],
    key_aspects: list[str],
    open_questions: list[str] | None = None,
    max_iterations: int = MAX_SECTION_ITERATIONS,
) -> SectionLoopResult:
    """Draft → evaluate → revise until pass or iteration limit."""
    feedback: list[str] = []
    history: list[dict[str, Any]] = []
    draft: DraftResult | None = None
    evaluation: EvaluationResult | None = None

    limit = max(1, int(max_iterations))
    for iteration in range(1, limit + 1):
        draft = generate_department_draft(
            department_id=department_id,
            metadata=metadata,
            key_aspects=key_aspects,
            open_questions=open_questions,
            feedback=feedback,
            iteration=iteration,
        )
        evaluation = evaluate_section(
            department_id=department_id,
            draft_content=draft.draft_content,
            key_aspects=key_aspects,
            metadata=metadata,
        )
        history.append(
            {
                "iteration": iteration,
                "passed": evaluation.passed,
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
                department_id=department_id,
                owner=draft.owner,
                draft_content=draft.draft_content,
                evaluation=evaluation,
                iterations=iteration,
                exhausted=False,
                history=history,
            )
        feedback = list(evaluation.feedback)

    assert draft is not None and evaluation is not None
    return SectionLoopResult(
        department_id=department_id,
        owner=draft.owner,
        draft_content=draft.draft_content,
        evaluation=evaluation,
        iterations=limit,
        exhausted=True,
        history=history,
    )
