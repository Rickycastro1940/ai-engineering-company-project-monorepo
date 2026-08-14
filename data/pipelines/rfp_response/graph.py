"""Dedicated Part 2 LangGraph — response generation + evaluation (not CX graph).

Flow per ticket (from Part 1 handoff, no PDF reparse):
  load_handoff → set_drafting → generate_evaluate_sections → finalize_status
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from data.pipelines.rfp_intake.constants import (
    DEPARTMENT_IDS,
    STATUS_DRAFTING,
    STATUS_INTAKE_COMPLETE,
    STATUS_NEEDS_HUMAN_REVIEW,
    STATUS_UNDER_EVALUATION,
    STATUS_WAITING_FOR_APPROVAL,
)
from data.pipelines.rfp_response.compliance_rules import MAX_SECTION_ITERATIONS
from data.pipelines.rfp_response.agents import (
    Part1DepartmentSummary,
    get_generator_agent,
)
from data.pipelines.rfp_response.handoff_consume import (
    PRIMARY_GENERATOR_INPUT,
    Part1HandoffNotReady,
    assert_part1_routing_ready,
    synthesizer_payload_from_handoff,
)
from data.pipelines.rfp_response.loop import SectionLoopResult, run_section_loop
from data.pipelines.rfp_response.part3_handoff import build_part3_handoff

REQUIRED_RESPONSE_NODES: tuple[str, ...] = (
    "load_handoff",
    "set_drafting",
    "generate_evaluate_sections",
    "finalize_status",
)


class RfpResponseState(TypedDict, total=False):
    ticket_id: str
    handoff: dict[str, Any]
    metadata: dict[str, Any]
    synthesizer_payload: dict[str, Any]
    part2_ready: bool
    intake_status: str
    status: str
    section_results: list[dict[str, Any]]
    average_iterations: float
    all_passed: bool
    error_message: str | None
    trace: list[dict[str, Any]]
    max_iterations: int
    part3_handoff: dict[str, Any]
    discarded: bool


def _event(state: RfpResponseState, node: str, **payload: Any) -> list[dict[str, Any]]:
    trace = list(state.get("trace") or [])
    trace.append({"node": node, "payload": payload})
    return trace


def load_handoff_node(state: RfpResponseState) -> dict[str, Any]:
    """Validate Part 1 routing handoff (ticket_id + synthesizer key_aspects)."""
    handoff = dict(state.get("handoff") or {})
    ticket_id = (state.get("ticket_id") or handoff.get("ticket_id") or "").strip()
    intake_status = str(
        state.get("intake_status") or handoff.get("status") or STATUS_INTAKE_COMPLETE
    )
    part2_ready = state.get("part2_ready")
    if part2_ready is None:
        part2_ready = bool(handoff.get("part2_ready", True))

    try:
        contract = assert_part1_routing_ready(
            ticket_id=ticket_id,
            status=intake_status,
            part2_ready=bool(part2_ready),
            handoff=handoff or None,
        )
    except Part1HandoffNotReady as exc:
        return {
            "ticket_id": ticket_id,
            "status": "failed",
            "error_message": str(exc),
            "trace": _event(state, "load_handoff", error=str(exc)),
        }

    payload = synthesizer_payload_from_handoff(contract)
    return {
        "ticket_id": ticket_id,
        "handoff": contract,
        "metadata": dict(payload.get("metadata") or {}),
        "synthesizer_payload": payload,
        "part2_ready": True,
        "intake_status": STATUS_INTAKE_COMPLETE,
        "error_message": None,
        "trace": _event(
            state,
            "load_handoff",
            ticket_id=ticket_id,
            work_streams=len(payload.get("work_streams") or []),
            source="part1_handoff_contract",
            primary_input=PRIMARY_GENERATOR_INPUT,
            queue_flag="part2_ready",
            db_field="part2_handoff_json",
            reparse_pdf_required=False,
        ),
    }


def set_drafting_node(state: RfpResponseState) -> dict[str, Any]:
    if state.get("error_message"):
        return {}
    return {
        "status": STATUS_DRAFTING,
        "trace": _event(state, "set_drafting", status=STATUS_DRAFTING),
    }


def generate_evaluate_sections_node(state: RfpResponseState) -> dict[str, Any]:
    if state.get("error_message"):
        return {}
    # Prefer synthesizer payload extracted from Part 1 handoff (not a parallel summary)
    payload = state.get("synthesizer_payload") or synthesizer_payload_from_handoff(
        state.get("handoff") or {}
    )
    metadata = dict(payload.get("metadata") or state.get("metadata") or {})
    max_iter = int(state.get("max_iterations") or MAX_SECTION_ITERATIONS)
    results: list[dict[str, Any]] = []
    trace = list(state.get("trace") or [])
    trace.append(
        {
            "node": "under_evaluation",
            "payload": {"status": STATUS_UNDER_EVALUATION},
        }
    )

    streams = [
        stream
        for stream in (payload.get("work_streams") or [])
        if stream.get("department_id")
    ]
    ticket_id = str(state.get("ticket_id") or payload.get("ticket_id") or "")

    def _run_stream(stream: dict[str, Any]) -> tuple[SectionLoopResult, str, int]:
        dept = stream.get("department_id") or ""
        summary = Part1DepartmentSummary.from_work_stream(
            stream, metadata=metadata, ticket_id=ticket_id
        )
        agent = get_generator_agent(dept)
        loop_result = run_section_loop(summary=summary, max_iterations=max_iter)
        return loop_result, agent.agent_name, len(summary.key_aspects)

    workers = max(1, min(4, len(streams)))
    gathered: list[tuple[SectionLoopResult, str, int]] = []
    if streams:
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="rfp-section-eval"
        ) as pool:
            futs = [pool.submit(_run_stream, stream) for stream in streams]
            for fut in as_completed(futs):
                gathered.append(fut.result())

    order = {d: i for i, d in enumerate(sorted(DEPARTMENT_IDS))}
    gathered.sort(key=lambda item: order.get(item[0].department_id, 99))

    for loop_result, agent_name, aspects_count in gathered:
        results.append(loop_result.to_dict())
        ev = loop_result.evaluation
        trace.append(
            {
                "node": "generate_evaluate_sections",
                "payload": {
                    "department_id": loop_result.department_id,
                    "generator_agent": agent_name,
                    "evaluator_agents": list(ev.evaluator_agents),
                    "evaluators_parallel": ev.parallel,
                    "iterations": loop_result.iterations,
                    "passed": ev.passed,
                    "exhausted": loop_result.exhausted,
                    "key_aspects_count": aspects_count,
                    "input": "part1_work_stream_key_aspects",
                    "part1_summary_used": True,
                    "kb_grounded": loop_result.kb_grounded,
                },
            }
        )

    iters = [r["iterations"] for r in results] or [0]
    avg = sum(iters) / len(iters)
    all_passed = bool(results) and all(r["passed"] for r in results)
    return {
        "status": STATUS_UNDER_EVALUATION,
        "section_results": results,
        "average_iterations": avg,
        "all_passed": all_passed,
        "trace": trace,
    }


def finalize_status_node(state: RfpResponseState) -> dict[str, Any]:
    if state.get("error_message"):
        return {
            "status": "failed",
            "discarded": False,
            "trace": _event(state, "finalize_status", error=state.get("error_message")),
        }
    sections = list(state.get("section_results") or [])
    all_passed = bool(state.get("all_passed"))
    exhausted_any = any(r.get("exhausted") for r in sections)
    if all_passed:
        status = STATUS_WAITING_FOR_APPROVAL
    else:
        # Iteration limit and/or remaining failures → human review, never discard
        status = STATUS_NEEDS_HUMAN_REVIEW
    part3 = build_part3_handoff(
        ticket_id=str(state.get("ticket_id") or ""),
        ticket_status=status,
        section_results=sections,
    )
    return {
        "status": status,
        "discarded": False,
        "part3_handoff": part3,
        "trace": _event(
            state,
            "finalize_status",
            status=status,
            all_passed=all_passed,
            exhausted_any=exhausted_any,
            discarded=False,
            part3_sections=len(part3.get("sections") or []),
            average_iterations=state.get("average_iterations"),
        ),
    }


def _after_load(state: RfpResponseState) -> str:
    if state.get("error_message"):
        return "end"
    return "set_drafting"


def build_rfp_response_graph() -> Any:
    graph = StateGraph(RfpResponseState)
    graph.add_node("load_handoff", load_handoff_node)
    graph.add_node("set_drafting", set_drafting_node)
    graph.add_node("generate_evaluate_sections", generate_evaluate_sections_node)
    graph.add_node("finalize_status", finalize_status_node)

    graph.add_edge(START, "load_handoff")
    graph.add_conditional_edges(
        "load_handoff",
        _after_load,
        {"set_drafting": "set_drafting", "end": END},
    )
    graph.add_edge("set_drafting", "generate_evaluate_sections")
    graph.add_edge("generate_evaluate_sections", "finalize_status")
    graph.add_edge("finalize_status", END)

    compiled = graph.compile()
    registered = set(compiled.get_graph().nodes)
    missing = [n for n in REQUIRED_RESPONSE_NODES if n not in registered]
    if missing:
        raise RuntimeError(f"RFP response graph missing nodes: {missing}")
    return compiled


_COMPILED = None


def get_compiled_rfp_response_graph() -> Any:
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_rfp_response_graph()
    return _COMPILED


def invoke_rfp_response_graph(
    *,
    ticket_id: str,
    handoff: dict[str, Any],
    max_iterations: int = MAX_SECTION_ITERATIONS,
    intake_status: str | None = None,
    part2_ready: bool | None = None,
) -> RfpResponseState:
    graph = get_compiled_rfp_response_graph()
    initial: RfpResponseState = {
        "ticket_id": ticket_id,
        "handoff": handoff,
        "intake_status": intake_status or str(handoff.get("status") or ""),
        "part2_ready": True if part2_ready is None else bool(part2_ready),
        "trace": [],
        "section_results": [],
        "max_iterations": max_iterations,
    }
    return graph.invoke(initial)
