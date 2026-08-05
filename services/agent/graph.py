"""Compile and run the Brasaland support-agent LangGraph.

The graph is **compiled before any execution** so structural errors fail at
build/startup time rather than in production. Checkpointing uses
``MemorySaver`` so each meaningful transition can be inspected or resumed via
``thread_id``.

Part 2 adds a read-only ticket tool node and conditional routing between RAG
and the incident manager based on the question content.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from services.agent.nodes import (
    answer_ticket_node,
    empty_question_node,
    generate_node,
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
    "retrieve",
    "generate",
    "no_context",
    "empty_question",
    "lookup_ticket",
    "answer_ticket",
    "ticket_fallback",
)

_CHECKPOINTER = MemorySaver()
_COMPILED_GRAPH = None


class GraphStructureError(ValueError):
    """Raised when the agent graph topology is invalid before compile/invoke."""


def _after_receive(state: AgentState) -> str:
    """Conditional edge: empty / ticket / rag / both."""
    route = state.get("route") or ""
    if route == "empty":
        return "empty_question"
    if route in ("ticket", "both"):
        return "lookup_ticket"
    return "retrieve"


def _after_lookup_ticket(state: AgentState) -> str:
    """After the ticket tool: continue to RAG, answer, or honest fallback."""
    route = state.get("route") or ""
    if route == "retrieve":
        return "retrieve"
    if route == "ticket_answer":
        return "answer_ticket"
    return "ticket_fallback"


def _after_retrieve(state: AgentState) -> str:
    """Conditional edge after retrieve (RAG and/or prior ticket result)."""
    route = state.get("route")
    if route == "error":
        return "end"
    if route == "no_context":
        return "no_context"
    if route == "ticket_answer":
        return "answer_ticket"
    if route == "ticket_fallback":
        return "ticket_fallback"
    return "generate"


def build_agent_graph() -> StateGraph:
    """Assemble nodes + conditional edges (not yet compiled)."""
    graph = StateGraph(AgentState)
    graph.add_node("receive_question", receive_question)
    graph.add_node("lookup_ticket", lookup_ticket_node)
    graph.add_node("answer_ticket", answer_ticket_node)
    graph.add_node("ticket_fallback", ticket_fallback_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("no_context", no_context_node)
    graph.add_node("empty_question", empty_question_node)

    graph.add_edge(START, "receive_question")
    graph.add_conditional_edges(
        "receive_question",
        _after_receive,
        {
            "empty_question": "empty_question",
            "lookup_ticket": "lookup_ticket",
            "retrieve": "retrieve",
        },
    )
    graph.add_conditional_edges(
        "lookup_ticket",
        _after_lookup_ticket,
        {
            "retrieve": "retrieve",
            "answer_ticket": "answer_ticket",
            "ticket_fallback": "ticket_fallback",
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
            "end": END,
        },
    )
    graph.add_edge("generate", END)
    graph.add_edge("no_context", END)
    graph.add_edge("empty_question", END)
    graph.add_edge("answer_ticket", END)
    graph.add_edge("ticket_fallback", END)
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
                "needs_rag": values.get("needs_rag"),
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
        "needs_rag": False,
        "ticket_query": None,
        "ticket_result": None,
        "sources_used": [],
        "steps": [],
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
        needs_rag=bool(final.get("needs_rag")),
    )
    save_trace(record)

    return {
        "trace_id": trace_id,
        "status": status,
        "answer": answer,
        "error": public_error,
        "steps": steps,
        "node_order": node_order,
        "sources_used": sources_used,
    }
