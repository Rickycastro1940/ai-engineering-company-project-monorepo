"""RFP response generation pipeline (Milestone 9 Part 2).

Builds on Part 1 classification + routing — does not rewrite intake.
Sole input: Part 1 routing handoff for tickets with
``status=intake_complete`` + ``part2_ready`` + validated
``ticket_id`` + synthesizer ``work_streams[].key_aspects``.

Never re-parses the PDF. Never invents a parallel summary path.
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
from data.pipelines.rfp_response.agents import (
    GENERATOR_AGENTS,
    DraftResult,
    Part1DepartmentSummary,
    get_generator_agent,
    run_generator_agent,
)
from data.pipelines.rfp_response.handoff_consume import (
    PRIMARY_GENERATOR_INPUT,
    Part1HandoffNotReady,
    assert_part1_routing_ready,
    synthesizer_payload_from_handoff,
)
from data.pipelines.rfp_response.evaluators import (
    EVALUATOR_AGENTS,
    EvaluationResult,
    evaluate_section,
)

__all__ = [
    "EVALUATOR_AGENTS",
    "EvaluationResult",
    "GENERATOR_AGENTS",
    "MAX_SECTION_ITERATIONS",
    "PRIMARY_GENERATOR_INPUT",
    "Part1DepartmentSummary",
    "Part1HandoffNotReady",
    "REQUIRED_RESPONSE_NODES",
    "ResponsePipelineResult",
    "assert_part1_routing_ready",
    "build_rfp_response_graph",
    "get_compiled_rfp_response_graph",
    "get_generator_agent",
    "invoke_rfp_response_graph",
    "run_generator_agent",
    "run_response_for_ticket",
    "run_response_pipeline",
    "run_section_loop",
    "synthesizer_payload_from_handoff",
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
    intake_status: str | None = None,
    part2_ready: bool | None = None,
) -> ResponsePipelineResult:
    """Run Part 2 from an already-loaded Part 1 handoff contract."""
    final = invoke_rfp_response_graph(
        ticket_id=ticket_id,
        handoff=handoff,
        max_iterations=max_iterations,
        intake_status=intake_status,
        part2_ready=part2_ready,
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


def run_response_for_ticket(
    ticket_id: str,
    *,
    max_iterations: int = MAX_SECTION_ITERATIONS,
) -> ResponsePipelineResult:
    """Canonical Part 2 entry: load Part 1 ready handoff from DB, then generate.

    Requires ``intake_complete`` + ``part2_ready`` + validated handoff JSON.
    """
    from services.rfp.store import load_ready_part2_handoff

    handoff, ticket_status, ready_flag = load_ready_part2_handoff(ticket_id)
    return run_response_pipeline(
        ticket_id=ticket_id,
        handoff=handoff,
        max_iterations=max_iterations,
        intake_status=ticket_status,
        part2_ready=ready_flag,
    )
