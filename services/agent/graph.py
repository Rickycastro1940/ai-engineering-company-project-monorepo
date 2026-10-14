"""Compiled Brasaland support graph.

Compiled once at import. A missing node or edge raises ``ValueError`` from
LangGraph before any question is served. ``MemorySaver`` checkpoints each
transition under the run's ``thread_id`` (the same value as ``trace_id``).
"""
from __future__ import annotations

import logging
import uuid

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from services.agent.nodes import (
    after_receive,
    after_retrieve,
    honest_answer,
    query_node,
    receive_question,
    retrieve_node,
)
from services.agent.state import AgentState
from services.agent.tracing import save_trace

logger = logging.getLogger("brasaland.agent")


class AgentGraphError(Exception):
    """The compiled graph raised. ``trace_id`` is safe to show to the client."""

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        super().__init__(f"Agent failed. Check trace {trace_id}.")


def build_agent_graph():
    builder = StateGraph(AgentState)
    builder.add_node("receive_question", receive_question)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("query", query_node)
    builder.add_node("honest_answer", honest_answer)
    builder.set_entry_point("receive_question")
    builder.add_conditional_edges(
        "receive_question",
        after_receive,
        {"retrieve": "retrieve", "end": END},
    )
    builder.add_conditional_edges(
        "retrieve",
        after_retrieve,
        {"query": "query", "honest": "honest_answer", "end": END},
    )
    builder.add_edge("query", END)
    builder.add_edge("honest_answer", END)
    return builder.compile(checkpointer=MemorySaver())


agent_graph = build_agent_graph()


def run_agent(question: str) -> dict:
    """Invoke the compiled graph once and store a queryable trace."""
    trace_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": trace_id}}
    initial: AgentState = {
        "question": question,
        "retrieved_context": None,
        "answer": None,
        "trace_steps": [],
        "error": None,
    }
    try:
        result = agent_graph.invoke(initial, config)
        snapshot = agent_graph.get_state(config)
    except Exception as error:
        logger.exception("support graph failed")
        save_trace(
            {
                "trace_id": trace_id,
                "question": (question or "").strip(),
                "answer": None,
                "error": "Agent failed. Check trace.",
                "trace_steps": [],
                "nodes": [],
                "checkpoint_id": None,
            }
        )
        raise AgentGraphError(trace_id) from error

    configurable = {}
    if snapshot is not None and getattr(snapshot, "config", None):
        configurable = snapshot.config.get("configurable") or {}
    steps = [dict(step) for step in (result.get("trace_steps") or [])]
    return save_trace(
        {
            "trace_id": trace_id,
            "question": result.get("question") or "",
            "answer": result.get("answer"),
            "error": result.get("error"),
            "trace_steps": steps,
            "nodes": [step.get("node") for step in steps],
            "checkpoint_id": configurable.get("checkpoint_id"),
        }
    )
