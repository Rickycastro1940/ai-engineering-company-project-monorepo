"""Single-responsibility LangGraph nodes for the Brasaland support agent.

Required nodes (Part 1 checklist)
---------------------------------
1. ``receive_question`` — accepts/normalizes the user question.
2. ``retrieve`` — calls ``data.pipelines.rag.retrieve`` (reuse, do not duplicate).
3. ``generate`` — calls ``data.pipelines.rag.generate_answer(question, context)``
   with the chunks the retrieve node already produced.

Never call the monolithic ``query()`` (retrieve + generate) inside a node.
"""

from __future__ import annotations

import time
from typing import Any

from data.pipelines.rag import NO_CONTEXT_ANSWER, generate_answer, retrieve

from services.agent.state import AgentState


def _step(
    state: AgentState,
    node_name: str,
    status: str,
    started: float,
    *,
    notes: str | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one safe, queryable node-step record."""
    return {
        "node_name": node_name,
        "sequence": len(state.get("steps") or []) + 1,
        "status": status,
        "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "notes": notes,
        "output": output or {},
    }


def receive_question(state: AgentState) -> dict[str, Any]:
    """Node 1 — receive the question.

    Normalizes whitespace and sets ``route`` so conditional edges can skip
    retrieval when the question is empty.
    """
    started = time.perf_counter()
    question = (state.get("question") or "").strip()
    if not question:
        return {
            "question": "",
            "route": "empty",
            "error": "empty_question",
            "answer": None,
            "steps": [
                _step(
                    state,
                    "receive_question",
                    "error",
                    started,
                    notes="empty question",
                    output={"accepted": False},
                )
            ],
        }
    return {
        "question": question,
        "route": "retrieve",
        "error": None,
        "steps": [
            _step(
                state,
                "receive_question",
                "ok",
                started,
                notes="question accepted",
                output={"accepted": True, "question_len": len(question)},
            )
        ],
    }


def retrieve_node(state: AgentState) -> dict[str, Any]:
    """Node 2 — run ``retrieve`` against the knowledge base.

    Reuses ``data.pipelines.rag.retrieve``; does not embed generation here.
    Sets ``route`` to ``generate`` or ``no_context`` based on whether any chunk
    cleared the score threshold.
    """
    started = time.perf_counter()
    try:
        chunks = retrieve(state["question"])
    except Exception as exc:  # noqa: BLE001 — surface as graph error, not stack to client
        return {
            "retrieved": [],
            "route": "error",
            "error": f"retrieval_failed:{type(exc).__name__}",
            "steps": [
                _step(
                    state,
                    "retrieve",
                    "error",
                    started,
                    notes=f"retrieval failed: {type(exc).__name__}",
                    output={"chunk_count": 0},
                )
            ],
        }

    route = "generate" if chunks else "no_context"
    return {
        "retrieved": chunks,
        "route": route,
        "error": None,
        "steps": [
            _step(
                state,
                "retrieve",
                "ok",
                started,
                notes=f"chunks={len(chunks)} route={route}",
                output={
                    "chunk_count": len(chunks),
                    "sources": [c.get("source_document") for c in chunks],
                    "scores": [c.get("_score") for c in chunks],
                },
            )
        ],
    }


def generate_node(state: AgentState) -> dict[str, Any]:
    """Node 3 — generate the final answer from already-retrieved context.

    Calls ``generate_answer(question, context)`` only. Does not call ``retrieve``
    or the monolithic ``query()``.
    """
    started = time.perf_counter()
    try:
        answer = generate_answer(state["question"], state.get("retrieved") or [])
    except Exception as exc:  # noqa: BLE001
        return {
            "answer": None,
            "error": f"generation_failed:{type(exc).__name__}",
            "route": "error",
            "steps": [
                _step(
                    state,
                    "generate",
                    "error",
                    started,
                    notes=f"generation failed: {type(exc).__name__}",
                )
            ],
        }
    return {
        "answer": answer,
        "error": None,
        "route": "done",
        "steps": [
            _step(
                state,
                "generate",
                "ok",
                started,
                notes="grounded answer",
                output={"answer_len": len(answer or "")},
            )
        ],
    }


def no_context_node(state: AgentState) -> dict[str, Any]:
    """Honest fallback when retrieve returns nothing above the score threshold."""
    started = time.perf_counter()
    return {
        "answer": NO_CONTEXT_ANSWER,
        "error": None,
        "route": "done",
        "steps": [
            _step(
                state,
                "no_context",
                "ok",
                started,
                notes="no chunks above threshold",
                output={"answer": NO_CONTEXT_ANSWER},
            )
        ],
    }


def empty_question_node(state: AgentState) -> dict[str, Any]:
    """Terminal path for an empty / whitespace-only question."""
    started = time.perf_counter()
    message = "Question cannot be empty."
    return {
        "answer": None,
        "error": "empty_question",
        "route": "done",
        "steps": [
            _step(
                state,
                "empty_question",
                "error",
                started,
                notes=message,
                output={"error": message},
            )
        ],
    }
