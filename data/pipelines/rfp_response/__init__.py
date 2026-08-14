"""RFP response generation pipeline (Milestone 9 Part 2).

Consumes Part 1 handoff (ticket_id + work_streams.key_aspects) — does not
re-parse the PDF. Each active department drafts a section, then readability /
relevance / compliance evaluators run in a generator–evaluator loop
(CONTEXT §5 guidelines, §3 iteration KPI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS
from data.pipelines.rfp_response.graph import (
    REQUIRED_RESPONSE_NODES,
    build_rfp_response_graph,
    get_compiled_rfp_response_graph,
    invoke_rfp_response_graph,
)
from data.pipelines.rfp_response.loop import run_section_loop

__all__ = [
    "MAX_SECTION_ITERATIONS",
    "REQUIRED_RESPONSE_NODES",
    "ResponsePipelineResult",
    "build_rfp_response_graph",
    "get_compiled_rfp_response_graph",
    "invoke_rfp_response_graph",
    "run_response_pipeline",
    "run_section_loop",
]


@dataclass
class ResponsePipelineResult:
    ticket_id: str
    status: str
    section_results: list[dict[str, Any]] = field(default_factory=list)
    average_iterations: float = 0.0
    all_passed: bool = False
    error_message: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "status": self.status,
            "section_results": list(self.section_results),
            "average_iterations": self.average_iterations,
            "all_passed": self.all_passed,
            "error_message": self.error_message,
            "trace": list(self.trace),
        }


def run_response_pipeline(
    *,
    ticket_id: str,
    handoff: dict[str, Any],
    max_iterations: int = MAX_SECTION_ITERATIONS,
) -> ResponsePipelineResult:
    """Run Part 2 for one ticket from a Part 1 handoff contract."""
    final = invoke_rfp_response_graph(
        ticket_id=ticket_id,
        handoff=handoff,
        max_iterations=max_iterations,
    )
    return ResponsePipelineResult(
        ticket_id=str(final.get("ticket_id") or ticket_id),
        status=str(final.get("status") or "failed"),
        section_results=list(final.get("section_results") or []),
        average_iterations=float(final.get("average_iterations") or 0.0),
        all_passed=bool(final.get("all_passed")),
        error_message=final.get("error_message"),
        trace=list(final.get("trace") or []),
    )
