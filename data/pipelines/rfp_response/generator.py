"""Facade: dispatch the per-department generator agent from Part 1 handoff fields.

Primary input is Part 1 routing handoff only:
  ticket_id + work_streams[].key_aspects (+ intake metadata / open_questions).

Does **not** re-ingest the raw PDF (no converter import, no pdf_path, no
markdown re-summary). Each CONTEXT department has its own generator agent
(see ``agents.py``) that writes that department's pricing-proposal section.
"""

from __future__ import annotations

from typing import Any

from data.pipelines.rfp_response.agents import (
    GENERATOR_AGENTS,
    DepartmentGeneratorAgent,
    DraftResult,
    MarketingGeneratorAgent,
    OperacionesGeneratorAgent,
    Part1DepartmentSummary,
    ProcurementGeneratorAgent,
    TrainingGeneratorAgent,
    get_generator_agent,
    run_generator_agent,
)

# Rejected if callers try to smuggle PDF / raw-markdown as generator input
_FORBIDDEN_GENERATOR_KWARGS = frozenset(
    {
        "pdf_path",
        "source_pdf_path",
        "pdf_bytes",
        "raw_pdf",
        "markdown_text",
        "markdown",
        "document_path",
    }
)

__all__ = [
    "GENERATOR_AGENTS",
    "DepartmentGeneratorAgent",
    "DraftResult",
    "MarketingGeneratorAgent",
    "OperacionesGeneratorAgent",
    "Part1DepartmentSummary",
    "ProcurementGeneratorAgent",
    "TrainingGeneratorAgent",
    "generate_department_draft",
    "get_generator_agent",
    "run_generator_agent",
]


def generate_department_draft(
    *,
    department_id: str,
    metadata: dict[str, Any],
    key_aspects: list[str],
    open_questions: list[str] | None = None,
    feedback: list[str] | None = None,
    iteration: int = 1,
    ticket_id: str | None = None,
    owner: str | None = None,
    label: str | None = None,
    **kwargs: Any,
) -> DraftResult:
    """Generate a pricing-proposal section via the department's generator agent.

    Builds a ``Part1DepartmentSummary`` from the handoff fields and dispatches
    to that department's agent. Generators must not re-ingest the raw PDF.
    """
    banned = _FORBIDDEN_GENERATOR_KWARGS.intersection(kwargs)
    if banned:
        raise TypeError(
            "Generators must not re-ingest the raw PDF as primary input; "
            f"forbidden kwargs: {sorted(banned)}. "
            "Use Part 1 handoff ticket_id + work_streams.key_aspects."
        )
    if not key_aspects:
        raise ValueError(
            "Generators require Part 1 work_streams.key_aspects "
            "(synthesizer payload) — PDF is not an accepted substitute"
        )

    summary = Part1DepartmentSummary.from_work_stream(
        {
            "department_id": department_id,
            "owner": owner or "",
            "label": label or "",
            "key_aspects": list(key_aspects),
            "open_questions": list(open_questions or []),
        },
        metadata=metadata,
        ticket_id=ticket_id,
    )
    return run_generator_agent(summary, feedback=feedback, iteration=iteration)
