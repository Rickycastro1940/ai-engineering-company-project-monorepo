"""Single-responsibility LangGraph nodes for the Brasaland support agent.

Required nodes (Part 1 + Part 2)
--------------------------------
1. ``receive_question`` — accepts/normalizes the user question and classifies
   whether RAG, the ticket tool, or both are needed.
2. ``retrieve`` — calls ``data.pipelines.rag.retrieve`` (reuse, do not duplicate).
3. ``generate`` — calls ``data.pipelines.rag.generate_answer(question, context)``
   with the chunks the retrieve node already produced.
4. ``lookup_ticket`` — read-only ticket tool against the incident manager.
5. ``answer_ticket`` / ``ticket_fallback`` — honest ticket answers / recovery.

Never call the monolithic ``query()`` (retrieve + generate) inside a node.
"""

from __future__ import annotations

import time
from typing import Any

from data.pipelines.rag import NO_CONTEXT_ANSWER, generate_answer, retrieve

from services.agent.state import AgentState
from services.agent.tools.contracts import TicketLookupInput, TicketLookupOutput
from services.agent.tools.routing import classify_sources
from services.agent.tools.ticket_lookup import (
    TICKET_FALLBACK_MESSAGE,
    format_ticket_answer,
    lookup_ticket,
)

# Node contract: this module imports retrieve + generate_answer only — never query().
_MONOLITHIC_QUERY_FORBIDDEN = True


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
    """Node 1 — receive the question and decide RAG vs ticket tool (or both)."""
    started = time.perf_counter()
    question = (state.get("question") or "").strip()
    if not question:
        return {
            "question": "",
            "route": "empty",
            "error": "empty_question",
            "answer": None,
            "needs_ticket": False,
            "needs_rag": False,
            "ticket_query": None,
            "ticket_result": None,
            "sources_used": [],
            "steps": [
                _step(
                    state,
                    "receive_question",
                    "error",
                    started,
                    notes="empty question",
                    output={"accepted": False, "needs_ticket": False, "needs_rag": False},
                )
            ],
        }

    decision = classify_sources(question)
    return {
        "question": question,
        "route": decision["route"],
        "error": None,
        "needs_ticket": decision["needs_ticket"],
        "needs_rag": decision["needs_rag"],
        "ticket_query": decision["ticket_query"],
        "ticket_result": None,
        "sources_used": [],
        "steps": [
            _step(
                state,
                "receive_question",
                "ok",
                started,
                notes=f"question accepted route={decision['route']}",
                output={
                    "accepted": True,
                    "question_len": len(question),
                    "needs_ticket": decision["needs_ticket"],
                    "needs_rag": decision["needs_rag"],
                    "route": decision["route"],
                    "ticket_query": decision["ticket_query"],
                },
            )
        ],
    }


def lookup_ticket_node(state: AgentState) -> dict[str, Any]:
    """Read-only ticket tool node — GET against the incident manager only."""
    started = time.perf_counter()
    raw_query = state.get("ticket_query") or {}
    try:
        query = TicketLookupInput.model_validate(raw_query)
    except Exception as exc:  # noqa: BLE001
        result = TicketLookupOutput(
            ok=False,
            tickets=[],
            error="invalid_input",
            message=f"Invalid ticket lookup input: {exc}",
        )
        return {
            "ticket_result": result.model_dump(),
            "route": "ticket_fallback" if not state.get("needs_rag") else "retrieve",
            "sources_used": ["ticket"],
            "steps": [
                _step(
                    state,
                    "lookup_ticket",
                    "error",
                    started,
                    notes="invalid ticket query",
                    output=result.model_dump(),
                )
            ],
        }

    result = lookup_ticket(query)
    if state.get("needs_rag"):
        next_route = "retrieve"
    elif result.ok and result.tickets:
        next_route = "ticket_answer"
    else:
        next_route = "ticket_fallback"

    status = "ok" if result.ok else "error"
    return {
        "ticket_result": result.model_dump(),
        "route": next_route,
        "sources_used": ["ticket"],
        "steps": [
            _step(
                state,
                "lookup_ticket",
                status,
                started,
                notes=(
                    f"ticket tool ok={result.ok} error={result.error} "
                    f"count={len(result.tickets)} next={next_route}"
                ),
                output={
                    "source": "ticket",
                    "ok": result.ok,
                    "error": result.error,
                    "ticket_count": len(result.tickets),
                    "ticket_ids": [t.incident_id for t in result.tickets],
                    "statuses": [t.status for t in result.tickets],
                    "duration_ms": result.duration_ms,
                    "next_route": next_route,
                },
            )
        ],
    }


def answer_ticket_node(state: AgentState) -> dict[str, Any]:
    """Format a ticket-only answer from a successful tool call (no invention)."""
    started = time.perf_counter()
    raw = state.get("ticket_result") or {}
    result = TicketLookupOutput.model_validate(raw)
    answer = format_ticket_answer(result)
    return {
        "answer": answer,
        "error": None,
        "route": "done",
        "steps": [
            _step(
                state,
                "answer_ticket",
                "ok",
                started,
                notes="answer from live incident manager",
                output={
                    "source": "ticket",
                    "answer": answer,
                    "ticket_count": len(result.tickets),
                },
            )
        ],
    }


def ticket_fallback_node(state: AgentState) -> dict[str, Any]:
    """Honest recovery when the ticket tool times out, errors, or finds nothing."""
    started = time.perf_counter()
    raw = state.get("ticket_result") or {}
    try:
        result = TicketLookupOutput.model_validate(raw)
        answer = format_ticket_answer(result)
        error_code = result.error or "service_error"
    except Exception:  # noqa: BLE001
        answer = TICKET_FALLBACK_MESSAGE
        error_code = "service_error"
    return {
        "answer": answer,
        "error": None,  # operational fallback is a successful honest answer
        "route": "done",
        "steps": [
            _step(
                state,
                "ticket_fallback",
                "ok",
                started,
                notes=f"ticket fallback reason={error_code}",
                output={
                    "source": "ticket_fallback",
                    "reason": error_code,
                    "answer": answer,
                },
            )
        ],
    }


def retrieve_node(state: AgentState) -> dict[str, Any]:
    """Node — run ``retrieve`` against the knowledge base.

    Reuses ``data.pipelines.rag.retrieve``; does not embed generation here.
    Sets ``route`` to ``generate`` or ``no_context`` based on whether any chunk
    cleared the score threshold. When a prior ticket result exists and RAG is
    empty, prefer answering from the ticket instead of inventing KB content.
    """
    started = time.perf_counter()
    try:
        chunks = retrieve(state["question"])
    except Exception as exc:  # noqa: BLE001 — surface as graph error, not stack to client
        return {
            "retrieved": [],
            "route": "error",
            "error": f"retrieval_failed:{type(exc).__name__}",
            "sources_used": ["rag"],
            "steps": [
                _step(
                    state,
                    "retrieve",
                    "error",
                    started,
                    notes=f"retrieval failed: {type(exc).__name__}",
                    output={"chunk_count": 0, "source": "rag"},
                )
            ],
        }

    ticket_raw = state.get("ticket_result")
    if chunks:
        route = "generate"
    elif ticket_raw and (ticket_raw.get("ok") and ticket_raw.get("tickets")):
        route = "ticket_answer"
    elif ticket_raw and not ticket_raw.get("ok"):
        route = "ticket_fallback"
    else:
        route = "no_context"

    return {
        "retrieved": chunks,
        "route": route,
        "error": None,
        "sources_used": ["rag"],
        "steps": [
            _step(
                state,
                "retrieve",
                "ok",
                started,
                notes=f"chunks={len(chunks)} route={route}",
                output={
                    "source": "rag",
                    "chunk_count": len(chunks),
                    "sources": [c.get("source_document") for c in chunks],
                    "scores": [c.get("_score") for c in chunks],
                },
            )
        ],
    }


def generate_node(state: AgentState) -> dict[str, Any]:
    """Generate the final answer from already-retrieved context (+ optional ticket)."""
    started = time.perf_counter()
    chunks = state.get("retrieved") or []
    if not chunks:
        from data.pipelines.rag import NO_CONTEXT_ANSWER as _NO

        return {
            "answer": _NO,
            "error": None,
            "route": "done",
            "steps": [
                _step(
                    state,
                    "generate",
                    "ok",
                    started,
                    notes="refused generation without retrieved context",
                    output={"answer": _NO, "grounded": False, "source": "rag"},
                )
            ],
        }
    try:
        answer = generate_answer(state["question"], chunks)
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

    ticket_raw = state.get("ticket_result")
    if ticket_raw:
        try:
            ticket_out = TicketLookupOutput.model_validate(ticket_raw)
            ticket_text = format_ticket_answer(ticket_out)
            answer = f"{answer}\n\nLive ticket data:\n{ticket_text}"
        except Exception:  # noqa: BLE001
            pass

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
                notes="grounded answer from retrieved KB context",
                output={
                    "answer_len": len(answer or ""),
                    "grounded": True,
                    "source": "rag",
                    "used_ticket": bool(ticket_raw),
                    "context_sources": [c.get("source_document") for c in chunks],
                },
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
                output={"answer": NO_CONTEXT_ANSWER, "source": "rag"},
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
