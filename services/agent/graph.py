"""Compile and run the Brasaland support-agent LangGraph.

The graph is **compiled before any execution** so structural errors fail at
build/startup time rather than in production. Checkpointing uses
``MemorySaver`` so each meaningful transition can be inspected or resumed via
``thread_id``.

Part 2 adds read-only ticket + inventory tool nodes and conditional routing
between RAG and those tools based on the question content.

Memory milestone extends the same graph with ``recall_memory`` /
``write_memory`` — it does **not** replace MCP ticket lookup or RAG.

Harness / guardrails (Milestone 8 Part 2) add ``input_guardrail`` and
``output_guardrail`` around that graph so CONTEXT-company.md restrictions are
enforced in code, not only in the system prompt.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from services.agent.harness.nodes import input_guardrail_node, output_guardrail_node
from services.agent.memory.confirmation import resolve_memory_confirmation_node
from services.agent.memory.nodes import recall_memory_node, write_memory_node
from services.agent.nodes import (
    answer_inventory_node,
    answer_ticket_node,
    decide_route_node,
    empty_question_node,
    generate_node,
    inventory_fallback_node,
    lookup_inventory_node,
    lookup_ticket_node,
    no_context_node,
    receive_question,
    retrieve_node,
    ticket_fallback_node,
)
from services.agent.state import AgentState
from services.agent.tracing import TraceRecord, save_trace

REQUIRED_NODES = (
    "receive_question",
    "input_guardrail",
    "resolve_memory_confirmation",
    "decide_route",
    "recall_memory",
    "retrieve",
    "generate",
    "no_context",
    "empty_question",
    "lookup_ticket",
    "answer_ticket",
    "ticket_fallback",
    "lookup_inventory",
    "answer_inventory",
    "inventory_fallback",
    "output_guardrail",
    "write_memory",
)

_CHECKPOINTER = MemorySaver()
_COMPILED_GRAPH = None


class GraphStructureError(ValueError):
    """Raised when the agent graph topology is invalid before compile/invoke."""


def _after_receive(state: AgentState) -> str:
    """Conditional edge: empty question → error path; else → input guardrail."""
    return "empty_question" if state.get("route") == "empty" else "input_guardrail"


def _after_input_guardrail(state: AgentState) -> str:
    """Blocked input never reaches tools, RAG, or the LLM."""
    if state.get("route") == "guardrail_blocked":
        return "end"
    return "resolve_memory_confirmation"


def _after_output_guardrail(state: AgentState) -> str:
    """Hard blocks skip memory writes so forbidden text is never stored."""
    if state.get("route") == "guardrail_blocked":
        return "end"
    return "write_memory"


def _after_resolve_memory_confirmation(state: AgentState) -> str:
    """After confirming/discarding a pending proposal: ack-only or continue."""
    if state.get("route") == "confirmation_done":
        return "end"
    return "decide_route"


def _after_decide_route(state: AgentState) -> str:
    """Always recall durable memory before tools/RAG (extends, does not replace)."""
    return "recall_memory"


def _after_recall_memory(state: AgentState) -> str:
    """Same routing as pre-memory decide_route — MCP tools and RAG unchanged."""
    route = state.get("route") or ""
    if route in ("ticket", "both", "ticket_inventory", "all"):
        return "lookup_ticket"
    if route in ("inventory", "inventory_rag"):
        return "lookup_inventory"
    return "retrieve"


def _after_lookup_ticket(state: AgentState) -> str:
    """After the ticket tool: inventory, RAG, answer, or honest fallback."""
    route = state.get("route") or ""
    if route == "lookup_inventory":
        return "lookup_inventory"
    if route == "retrieve":
        return "retrieve"
    if route == "ticket_answer":
        return "answer_ticket"
    return "ticket_fallback"


def _after_lookup_inventory(state: AgentState) -> str:
    """After the inventory tool: RAG, answer, or honest fallback."""
    route = state.get("route") or ""
    if route == "retrieve":
        return "retrieve"
    if route == "inventory_answer":
        return "answer_inventory"
    return "inventory_fallback"


def _after_retrieve(state: AgentState) -> str:
    """Conditional edge after retrieve (RAG and/or prior tool results)."""
    route = state.get("route")
    if route == "error":
        return "end"
    if route == "no_context":
        return "no_context"
    if route == "ticket_answer":
        return "answer_ticket"
    if route == "ticket_fallback":
        return "ticket_fallback"
    if route == "inventory_answer":
        return "answer_inventory"
    if route == "inventory_fallback":
        return "inventory_fallback"
    return "generate"


def build_agent_graph() -> StateGraph:
    """Assemble nodes + conditional edges (not yet compiled)."""
    graph = StateGraph(AgentState)
    graph.add_node("receive_question", receive_question)
    graph.add_node("input_guardrail", input_guardrail_node)
    graph.add_node("resolve_memory_confirmation", resolve_memory_confirmation_node)
    graph.add_node("output_guardrail", output_guardrail_node)
    graph.add_node("decide_route", decide_route_node)
    graph.add_node("recall_memory", recall_memory_node)
    graph.add_node("lookup_ticket", lookup_ticket_node)
    graph.add_node("answer_ticket", answer_ticket_node)
    graph.add_node("ticket_fallback", ticket_fallback_node)
    graph.add_node("lookup_inventory", lookup_inventory_node)
    graph.add_node("answer_inventory", answer_inventory_node)
    graph.add_node("inventory_fallback", inventory_fallback_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("no_context", no_context_node)
    graph.add_node("empty_question", empty_question_node)
    graph.add_node("write_memory", write_memory_node)

    graph.add_edge(START, "receive_question")
    graph.add_conditional_edges(
        "receive_question",
        _after_receive,
        {
            "empty_question": "empty_question",
            "input_guardrail": "input_guardrail",
        },
    )
    graph.add_conditional_edges(
        "input_guardrail",
        _after_input_guardrail,
        {
            "resolve_memory_confirmation": "resolve_memory_confirmation",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "resolve_memory_confirmation",
        _after_resolve_memory_confirmation,
        {
            "decide_route": "decide_route",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "decide_route",
        _after_decide_route,
        {"recall_memory": "recall_memory"},
    )
    graph.add_conditional_edges(
        "recall_memory",
        _after_recall_memory,
        {
            "lookup_ticket": "lookup_ticket",
            "lookup_inventory": "lookup_inventory",
            "retrieve": "retrieve",
        },
    )
    graph.add_conditional_edges(
        "lookup_ticket",
        _after_lookup_ticket,
        {
            "lookup_inventory": "lookup_inventory",
            "retrieve": "retrieve",
            "answer_ticket": "answer_ticket",
            "ticket_fallback": "ticket_fallback",
        },
    )
    graph.add_conditional_edges(
        "lookup_inventory",
        _after_lookup_inventory,
        {
            "retrieve": "retrieve",
            "answer_inventory": "answer_inventory",
            "inventory_fallback": "inventory_fallback",
        },
    )
    graph.add_conditional_edges(
        "retrieve",
        _after_retrieve,
        {
            "generate": "generate",
            "no_context": "no_context",
            "answer_ticket": "answer_ticket",
            "ticket_fallback": "ticket_fallback",
            "answer_inventory": "answer_inventory",
            "inventory_fallback": "inventory_fallback",
            "end": END,
        },
    )
    # Successful answers pass output guardrails before any memory write.
    graph.add_edge("generate", "output_guardrail")
    graph.add_edge("answer_ticket", "output_guardrail")
    graph.add_edge("answer_inventory", "output_guardrail")
    graph.add_conditional_edges(
        "output_guardrail",
        _after_output_guardrail,
        {
            "write_memory": "write_memory",
            "end": END,
        },
    )
    graph.add_edge("write_memory", END)
    # Fallbacks / empty / no-context do not learn failed or unknown outcomes.
    graph.add_edge("no_context", END)
    graph.add_edge("empty_question", END)
    graph.add_edge("ticket_fallback", END)
    graph.add_edge("inventory_fallback", END)
    return graph


def validate_graph_structure(graph: StateGraph) -> None:
    """Fail clearly on structural problems before ``compile()`` / invoke."""
    registered = set(graph.nodes.keys()) - {"__start__", "__end__"}
    missing = [name for name in REQUIRED_NODES if name not in registered]
    if missing:
        raise GraphStructureError(
            f"Agent graph is missing required node(s): {', '.join(missing)}. "
            "Fix the topology before compile/invoke."
        )


def compile_agent_graph(*, checkpointer: Any | None = None):
    """Build, validate, and compile the agent graph."""
    graph = build_agent_graph()
    validate_graph_structure(graph)
    return graph.compile(checkpointer=checkpointer or _CHECKPOINTER)


def get_compiled_graph():
    """Return the process-wide compiled graph (compiled once, reused)."""
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = compile_agent_graph()
    return _COMPILED_GRAPH


def inspect_checkpoints(thread_id: str, *, graph: Any | None = None) -> list[dict[str, Any]]:
    """Return checkpoint snapshots for a run (one per meaningful transition)."""
    compiled = graph or get_compiled_graph()
    config = {"configurable": {"thread_id": thread_id}}
    history: list[dict[str, Any]] = []
    for i, snapshot in enumerate(compiled.get_state_history(config)):
        values = dict(snapshot.values or {})
        history.append(
            {
                "index": i,
                "next": list(snapshot.next or []),
                "created_at": getattr(snapshot, "created_at", None),
                "question": values.get("question"),
                "route": values.get("route"),
                "answer": values.get("answer"),
                "error": values.get("error"),
                "retrieved_count": len(values.get("retrieved") or []),
                "step_count": len(values.get("steps") or []),
                "node_order": [s.get("node_name") for s in (values.get("steps") or [])],
                "sources_used": list(values.get("sources_used") or []),
                "needs_ticket": values.get("needs_ticket"),
                "needs_inventory": values.get("needs_inventory"),
                "needs_rag": values.get("needs_rag"),
                "memory_hit_count": len(values.get("memory_hits") or []),
                "guardrail": values.get("guardrail"),
            }
        )
    history.reverse()
    for i, item in enumerate(history):
        item["index"] = i
    return history


def run_agent(question: str, *, thread_id: str | None = None) -> dict[str, Any]:
    """Invoke the **already-compiled** graph once and persist a queryable trace."""
    graph = get_compiled_graph()
    trace_id = thread_id or uuid4().hex
    started_at = datetime.now(UTC)
    perf_start = time.perf_counter()

    initial: AgentState = {
        "question": question or "",
        "retrieved": [],
        "answer": None,
        "error": None,
        "route": "",
        "needs_ticket": False,
        "needs_inventory": False,
        "needs_rag": False,
        "ticket_query": None,
        "ticket_result": None,
        "inventory_query": None,
        "inventory_result": None,
        "memory_hits": [],
        "memory_writes": [],
        "memory_proposal": None,
        "memory_pending_proposal": None,
        "memory_confirmation": None,
        "memory_self_evaluations": [],
        "sources_used": [],
        "steps": [],
        "guardrail": None,
    }

    try:
        final: AgentState = graph.invoke(
            initial,
            config={"configurable": {"thread_id": trace_id}},
        )
    except Exception as exc:  # noqa: BLE001
        ended_at = datetime.now(UTC)
        record = TraceRecord(
            trace_id=trace_id,
            status="error",
            question=question or "",
            answer=None,
            error=f"graph_failed:{type(exc).__name__}",
            steps=[],
            started_at=started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            duration_ms=max(0, int((time.perf_counter() - perf_start) * 1000)),
            node_order=[],
            sources_used=[],
        )
        save_trace(record)
        return {
            "trace_id": trace_id,
            "status": "error",
            "answer": None,
            "error": "The agent failed while processing the question.",
            "steps": [],
            "node_order": [],
            "sources_used": [],
        }

    ended_at = datetime.now(UTC)
    steps = list(final.get("steps") or [])
    node_order = [step["node_name"] for step in steps]
    sources_used = list(final.get("sources_used") or [])
    error = final.get("error")
    answer = final.get("answer")

    if error == "empty_question":
        status = "error"
        public_error = "Question cannot be empty."
    elif error:
        status = "error"
        public_error = "The agent failed while processing the question."
    else:
        status = "ok"
        public_error = None

    record = TraceRecord(
        trace_id=trace_id,
        status=status,
        question=final.get("question") or question or "",
        answer=answer,
        error=error,
        steps=steps,
        started_at=started_at.isoformat(),
        ended_at=ended_at.isoformat(),
        duration_ms=max(0, int((time.perf_counter() - perf_start) * 1000)),
        node_order=node_order,
        retrieved_count=len(final.get("retrieved") or []),
        route=final.get("route"),
        sources_used=sources_used,
        needs_ticket=bool(final.get("needs_ticket")),
        needs_inventory=bool(final.get("needs_inventory")),
        needs_rag=bool(final.get("needs_rag")),
    )
    save_trace(record)

    from services.agent.tracing import enrich_trace_sources

    source_fields = enrich_trace_sources(node_order=node_order, sources_used=sources_used)
    return {
        "trace_id": trace_id,
        "status": status,
        "answer": answer,
        "error": public_error,
        "steps": steps,
        "node_order": node_order,
        "sources_used": source_fields["sources_used"],
        "sources_order": source_fields["sources_order"],
        "source_summary": source_fields["source_summary"],
        "memory_hits": list(final.get("memory_hits") or []),
        "memory_writes": list(final.get("memory_writes") or []),
        "memory_pending_proposal": final.get("memory_pending_proposal"),
        "memory_confirmation": final.get("memory_confirmation"),
        "guardrail": final.get("guardrail"),
    }
