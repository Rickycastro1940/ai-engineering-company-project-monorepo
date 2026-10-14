"""Single-responsibility nodes for the support graph.

``retrieve`` and ``generate_answer`` stay in ``data/pipelines/rag.py``.
This module does not call ``query()``, which would retrieve again.
"""
from __future__ import annotations

from data.pipelines.rag import INSUFFICIENT, generate_answer, retrieve
from services.agent.state import AgentState
from services.safe_errors import ExternalServiceError


def receive_question(state: AgentState) -> dict:
    """Normalize the question and record that this run started."""
    question = (state.get("question") or "").strip()
    if not question:
        return {
            "question": "",
            "error": "Question cannot be empty.",
            "trace_steps": [
                {
                    "node": "receive_question",
                    "order": 1,
                    "output_summary": "empty question",
                }
            ],
        }
    return {
        "question": question,
        "error": None,
        "trace_steps": [
            {
                "node": "receive_question",
                "order": 1,
                "output_summary": "question accepted",
            }
        ],
    }


def retrieve_node(state: AgentState) -> dict:
    """Call ``data.pipelines.rag.retrieve`` and keep chunks that cleared the threshold."""
    try:
        chunks = retrieve(state["question"])
    except ExternalServiceError:
        return {
            "retrieved_context": [],
            "error": "Agent failed during retrieval.",
            "trace_steps": [
                {
                    "node": "retrieve",
                    "order": 2,
                    "output_summary": "retrieval unavailable",
                }
            ],
        }
    return {
        "retrieved_context": chunks,
        "trace_steps": [
            {
                "node": "retrieve",
                "order": 2,
                "output_summary": f"{len(chunks)} chunks above threshold",
            }
        ],
    }


def query_node(state: AgentState) -> dict:
    """Call ``generate_answer`` with the context the retrieve node already produced."""
    context = list(state.get("retrieved_context") or [])
    try:
        answer = generate_answer(state.get("question") or "", context)
    except ExternalServiceError:
        return {
            "error": "Agent failed during generation.",
            "trace_steps": [
                {
                    "node": "query",
                    "order": 3,
                    "output_summary": "generation unavailable",
                }
            ],
        }
    return {
        "answer": answer,
        "trace_steps": [
            {
                "node": "query",
                "order": 3,
                "output_summary": f"answer generated from {len(context)} chunks",
            }
        ],
    }


def honest_answer(state: AgentState) -> dict:
    """No chunk cleared the threshold, so do not generate from empty context."""
    return {
        "answer": INSUFFICIENT,
        "trace_steps": [
            {
                "node": "honest_answer",
                "order": 3,
                "output_summary": "no context above threshold",
            }
        ],
    }


def after_receive(state: AgentState) -> str:
    if state.get("error") or not (state.get("question") or "").strip():
        return "end"
    return "retrieve"


def after_retrieve(state: AgentState) -> str:
    if state.get("error"):
        return "end"
    if not state.get("retrieved_context"):
        return "honest"
    return "query"
