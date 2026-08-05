"""Compile and run the Brasaland support-agent LangGraph.

The graph is **compiled before any execution** so structural errors fail at
build/startup time rather than in production. Checkpointing uses
``MemorySaver`` so each meaningful transition can be inspected or resumed via
``thread_id``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from services.agent.nodes import (
    empty_question_node,
    generate_node,
    no_context_node,
    receive_question,
    retrieve_node,
)
from services.agent.state import AgentState
from services.agent.tracing import TraceRecord, save_trace

REQUIRED_NODES = (
    "receive_question",
    "retrieve",
    "generate",
    "no_context",
    "empty_question",
)

_CHECKPOINTER = MemorySaver()
_COMPILED_GRAPH = None


class GraphStructureError(ValueError):
    """Raised when the agent graph topology is invalid before compile/invoke."""


def _after_receive(state: AgentState) -> str:
    """Conditional edge: empty question → error path; else → retrieve."""
    return "empty_question" if state.get("route") == "empty" else "retrieve"


def _after_retrieve(state: AgentState) -> str:
    """Conditional edge: no chunks above threshold → no_context; else → generate."""
    route = state.get("route")
    if route == "error":
        return "end"
    if route == "no_context":
        return "no_context"
    return "generate"


def build_agent_graph() -> StateGraph:
    """Assemble nodes + conditional edges (not yet compiled)."""
    graph = StateGraph(AgentState)
    graph.add_node("receive_question", receive_question)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("no_context", no_context_node)
    graph.add_node("empty_question", empty_question_node)

    graph.add_edge(START, "receive_question")
    # Real conditions — not a hardcoded fixed sequence.
    graph.add_conditional_edges(
        "receive_question",
        _after_receive,
        {"empty_question": "empty_question", "retrieve": "retrieve"},
    )
    graph.add_conditional_edges(
        "retrieve",
        _after_retrieve,
        {"generate": "generate", "no_context": "no_context", "end": END},
    )
    graph.add_edge("generate", END)
    graph.add_edge("no_context", END)
    graph.add_edge("empty_question", END)
    return graph


def validate_graph_structure(graph: StateGraph) -> None:
    """Fail clearly on structural problems before ``compile()`` / invoke.

    Checks that the required single-responsibility nodes are registered. This
    catches mistyped node names and incomplete graphs at build time.
    """
    registered = set(graph.nodes.keys()) - {"__start__", "__end__"}
    missing = [name for name in REQUIRED_NODES if name not in registered]
    if missing:
        raise GraphStructureError(
            f"Agent graph is missing required node(s): {', '.join(missing)}. "
            "Fix the topology before compile/invoke."
        )


def compile_agent_graph(*, checkpointer: Any | None = None):
    """Build, validate, and compile the agent graph.

    Compilation (plus ``validate_graph_structure``) must succeed before any
    ``invoke``. Structural problems raise ``GraphStructureError`` / LangGraph
    errors at this stage — not during a live request.
    """
    graph = build_agent_graph()
    validate_graph_structure(graph)
    return graph.compile(checkpointer=checkpointer or _CHECKPOINTER)


def get_compiled_graph():
    """Return the process-wide compiled graph (compiled once, reused)."""
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = compile_agent_graph()
    return _COMPILED_GRAPH


def run_agent(question: str, *, thread_id: str | None = None) -> dict[str, Any]:
    """Invoke the **already-compiled** graph once and persist a queryable trace.

    Returns a dict with ``answer``, ``trace_id``, ``status``, ``steps``, and
    ``error`` — never a raw exception traceback.
    """
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
        )
        save_trace(record)
        return {
            "trace_id": trace_id,
            "status": "error",
            "answer": None,
            "error": "The agent failed while processing the question.",
            "steps": [],
            "node_order": [],
        }

    ended_at = datetime.now(UTC)
    steps = list(final.get("steps") or [])
    node_order = [step["node_name"] for step in steps]
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
    )
    save_trace(record)

    return {
        "trace_id": trace_id,
        "status": status,
        "answer": answer,
        "error": public_error,
        "steps": steps,
        "node_order": node_order,
    }
