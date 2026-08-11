"""Single-responsibility LangGraph nodes for the Brasaland support agent.

Required nodes (Part 1 + Part 2)
--------------------------------
1. ``receive_question`` — accepts/normalizes the user question.
2. ``decide_route`` — conditional router: RAG, ticket tool, or both (from
   question content; user does not pick the source).
3. ``retrieve`` — calls ``data.pipelines.rag.retrieve`` (reuse, do not duplicate).
4. ``generate`` — one model call via ``generate_agent_turn`` → user ``answer``
   plus optional ``memory_proposal`` (same agent; not a second LLM call).
   Reuses RAG grounding rules (``SYSTEM_PROMPT`` / client from ``data.pipelines.rag``).
5. ``lookup_ticket`` — ticket status via company-tools MCP (not direct HTTP).
6. ``answer_ticket`` / ``ticket_fallback`` — honest ticket answers / recovery.
7. ``recall_memory`` / ``write_memory`` — durable semantic memory that **extends**
   the MCP + RAG agent (never replaces tools or retrieval).

Never call the monolithic ``query()`` (retrieve + generate) inside a node.
"""

from __future__ import annotations

import time
from typing import Any

from data.pipelines.rag import NO_CONTEXT_ANSWER, generate_answer, retrieve

from services.agent.generation import generate_agent_turn
from services.agent.memory.proposal import MemoryProposal
from services.agent.state import AgentState
from services.agent.tools.contracts import (
    InventoryLookupInput,
    InventoryLookupOutput,
    TicketLookupInput,
    TicketLookupOutput,
)
from services.agent.tools.routing import classify_sources
from services.agent.tools.inventory_lookup import (
    INVENTORY_FALLBACK_MESSAGE,
    INVENTORY_LOOKUP_TIMEOUT_SECONDS,
    format_inventory_answer,
    honest_inventory_fallback_answer,
    lookup_inventory,
)
from services.agent.tools.mcp_incidents import lookup_ticket_via_mcp
from services.agent.tools.ticket_lookup import (
    TICKET_FALLBACK_MESSAGE,
    TICKET_LOOKUP_TIMEOUT_SECONDS,
    format_ticket_answer,
    honest_ticket_fallback_answer,
)

# Node contract: retrieve from rag; generate via structured agent turn — never query().
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
    """Node 1 — receive/normalize the question only (no source decision here)."""
    started = time.perf_counter()
    question = (state.get("question") or "").strip()
    if not question:
        return {
            "question": "",
            "route": "empty",
            "error": "empty_question",
            "answer": None,
            "needs_ticket": False,
            "needs_inventory": False,
            "needs_rag": False,
            "ticket_query": None,
            "ticket_result": None,
            "inventory_query": None,
            "inventory_result": None,
            "sources_used": [],
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
        "route": "decide",
        "error": None,
        "ticket_result": None,
        "inventory_result": None,
        "sources_used": [],
        "steps": [
            _step(
                state,
                "receive_question",
                "ok",
                started,
                notes="question accepted; next=decide_route",
                output={"accepted": True, "question_len": len(question)},
            )
        ],
    }


def decide_route_node(state: AgentState) -> dict[str, Any]:
    """Conditional router — ticket tool, inventory tool, RAG, or a combination.

    The user never specifies which source to use. Inspects the question and sets
    ``needs_ticket`` / ``needs_inventory`` / ``needs_rag`` plus ``route``.
    """
    started = time.perf_counter()
    question = state.get("question") or ""
    decision = classify_sources(question)
    label = {
        "ticket": "ticket_tool",
        "inventory": "inventory_tool",
        "retrieve": "rag",
        "both": "ticket_tool_and_rag",
        "inventory_rag": "inventory_tool_and_rag",
        "ticket_inventory": "ticket_and_inventory",
        "all": "ticket_inventory_and_rag",
    }.get(decision["route"], decision["route"])
    return {
        "route": decision["route"],
        "needs_ticket": decision["needs_ticket"],
        "needs_inventory": decision["needs_inventory"],
        "needs_rag": decision["needs_rag"],
        "ticket_query": decision["ticket_query"],
        "inventory_query": decision["inventory_query"],
        "steps": [
            _step(
                state,
                "decide_route",
                "ok",
                started,
                notes=(
                    f"route={decision['route']} "
                    f"needs_ticket={decision['needs_ticket']} "
                    f"needs_inventory={decision['needs_inventory']} "
                    f"needs_rag={decision['needs_rag']}"
                ),
                output={
                    "route": decision["route"],
                    "needs_ticket": decision["needs_ticket"],
                    "needs_inventory": decision["needs_inventory"],
                    "needs_rag": decision["needs_rag"],
                    "ticket_query": decision["ticket_query"],
                    "inventory_query": decision["inventory_query"],
                    "decision": label,
                },
            )
        ],
    }


def _next_after_ticket(state: AgentState, result: TicketLookupOutput) -> str:
    if state.get("needs_inventory"):
        return "lookup_inventory"
    if state.get("needs_rag"):
        return "retrieve"
    if result.ok and result.tickets:
        return "ticket_answer"
    return "ticket_fallback"


def lookup_ticket_node(state: AgentState) -> dict[str, Any]:
    """Ticket tool node — Incidents Manager via MCP (langchain-mcp-adapters).

    Direct HTTP ``ticket_lookup.lookup_ticket`` is deprecated for graph use.
    This node always goes through the company-tools MCP server.
    """
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
            "route": _next_after_ticket(state, result),
            "sources_used": ["ticket"],
            "steps": [
                _step(
                    state,
                    "lookup_ticket",
                    "error",
                    started,
                    notes="invalid ticket query",
                    output={**result.model_dump(), "timeout_seconds": TICKET_LOOKUP_TIMEOUT_SECONDS},
                )
            ],
        }

    # MCP client path — never call the Incidents Manager HTTP API directly.
    result = lookup_ticket_via_mcp(query, timeout_seconds=TICKET_LOOKUP_TIMEOUT_SECONDS)
    next_route = _next_after_ticket(state, result)

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
                    f"mcp ticket tool ok={result.ok} error={result.error} "
                    f"count={len(result.tickets)} next={next_route} "
                    f"timeout_s={TICKET_LOOKUP_TIMEOUT_SECONDS}"
                ),
                output={
                    "source": "ticket",
                    "via": "mcp",
                    "ok": result.ok,
                    "error": result.error,
                    "ticket_count": len(result.tickets),
                    "ticket_ids": [t.incident_id for t in result.tickets],
                    "statuses": [t.status for t in result.tickets],
                    "duration_ms": result.duration_ms,
                    "timeout_seconds": TICKET_LOOKUP_TIMEOUT_SECONDS,
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
    # Ticket rows are not CONTEXT memorable domains — no memory_proposal.
    no_proposal = MemoryProposal.nothing_to_remember(
        "ticket_path_not_in_context_memorable_domains"
    ).as_dict()
    return {
        "answer": answer,
        "memory_proposal": no_proposal,
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
                    "memory_proposal": no_proposal,
                },
            )
        ],
    }


def ticket_fallback_node(state: AgentState) -> dict[str, Any]:
    """Fallback path — tool failed or ticket missing; never invent a status.

    Routes here from ``lookup_ticket`` when the incident call times out, errors,
    returns 404 / empty, or input is invalid. The answer always includes
    ``I couldn't confirm that ticket's status right now`` and never fabricates
    ABIERTO / CERRADO / DESCARTADO.
    """
    started = time.perf_counter()
    raw = state.get("ticket_result") or {}
    try:
        result = TicketLookupOutput.model_validate(raw)
        answer = honest_ticket_fallback_answer(result)
        error_code = result.error or "service_error"
    except Exception:  # noqa: BLE001
        answer = TICKET_FALLBACK_MESSAGE
        error_code = "service_error"

    # Defense in depth: fallback answers must never look like a live status.
    lowered = answer.casefold()
    if any(
        marker in lowered
        for marker in ("status=abierto", "status=cerrado", "status=descartado")
    ):
        answer = TICKET_FALLBACK_MESSAGE

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
                notes=f"ticket fallback reason={error_code} (no invented status)",
                output={
                    "source": "ticket_fallback",
                    "reason": error_code,
                    "answer": answer,
                    "invented_status": False,
                    "fallback_message": TICKET_FALLBACK_MESSAGE,
                },
            )
        ],
    }


def _next_after_inventory(state: AgentState, result: InventoryLookupOutput) -> str:
    if state.get("needs_rag"):
        return "retrieve"
    if result.ok and result.products:
        return "inventory_answer"
    return "inventory_fallback"


def lookup_inventory_node(state: AgentState) -> dict[str, Any]:
    """Read-only inventory tool node — GET /inventory/products only.

    Separate from the ticket tool (single responsibility). Explicit 5s timeout;
    failures route to ``inventory_fallback`` — never invent stock quantities.
    """
    started = time.perf_counter()
    raw_query = state.get("inventory_query") or {}
    try:
        query = InventoryLookupInput.model_validate(raw_query)
    except Exception as exc:  # noqa: BLE001
        result = InventoryLookupOutput(
            ok=False,
            products=[],
            error="invalid_input",
            message=f"Invalid inventory lookup input: {exc}",
        )
        next_route = _next_after_inventory(state, result)
        return {
            "inventory_result": result.model_dump(),
            "route": next_route,
            "sources_used": ["inventory"],
            "steps": [
                _step(
                    state,
                    "lookup_inventory",
                    "error",
                    started,
                    notes="invalid inventory query",
                    output={
                        **result.model_dump(),
                        "timeout_seconds": INVENTORY_LOOKUP_TIMEOUT_SECONDS,
                    },
                )
            ],
        }

    result = lookup_inventory(query, timeout_seconds=INVENTORY_LOOKUP_TIMEOUT_SECONDS)
    next_route = _next_after_inventory(state, result)
    status = "ok" if result.ok else "error"
    return {
        "inventory_result": result.model_dump(),
        "route": next_route,
        "sources_used": ["inventory"],
        "steps": [
            _step(
                state,
                "lookup_inventory",
                status,
                started,
                notes=(
                    f"inventory tool ok={result.ok} error={result.error} "
                    f"count={len(result.products)} next={next_route} "
                    f"timeout_s={INVENTORY_LOOKUP_TIMEOUT_SECONDS}"
                ),
                output={
                    "source": "inventory",
                    "ok": result.ok,
                    "error": result.error,
                    "product_count": len(result.products),
                    "product_ids": [p.product_id for p in result.products],
                    "quantities": [p.quantity for p in result.products],
                    "duration_ms": result.duration_ms,
                    "timeout_seconds": INVENTORY_LOOKUP_TIMEOUT_SECONDS,
                    "next_route": next_route,
                },
            )
        ],
    }


def answer_inventory_node(state: AgentState) -> dict[str, Any]:
    """Format inventory answer from a successful tool call (optionally + ticket)."""
    started = time.perf_counter()
    raw = state.get("inventory_result") or {}
    result = InventoryLookupOutput.model_validate(raw)
    answer = format_inventory_answer(result)
    ticket_raw = state.get("ticket_result")
    if ticket_raw:
        try:
            ticket_out = TicketLookupOutput.model_validate(ticket_raw)
            ticket_text = format_ticket_answer(ticket_out)
            answer = f"{ticket_text}\n\n{answer}"
        except Exception:  # noqa: BLE001
            pass
    no_proposal = MemoryProposal.nothing_to_remember(
        "inventory_path_not_in_context_memorable_domains"
    ).as_dict()
    return {
        "answer": answer,
        "memory_proposal": no_proposal,
        "error": None,
        "route": "done",
        "steps": [
            _step(
                state,
                "answer_inventory",
                "ok",
                started,
                notes="answer from live inventory manager",
                output={
                    "source": "inventory",
                    "answer": answer,
                    "product_count": len(result.products),
                    "used_ticket": bool(ticket_raw),
                    "memory_proposal": no_proposal,
                },
            )
        ],
    }


def inventory_fallback_node(state: AgentState) -> dict[str, Any]:
    """Fallback when inventory tool fails — never invent a stock quantity."""
    started = time.perf_counter()
    raw = state.get("inventory_result") or {}
    try:
        result = InventoryLookupOutput.model_validate(raw)
        answer = honest_inventory_fallback_answer(result)
        error_code = result.error or "service_error"
    except Exception:  # noqa: BLE001
        answer = INVENTORY_FALLBACK_MESSAGE
        error_code = "service_error"

    if "quantity=" in answer.casefold() and "couldn't confirm" not in answer.casefold():
        answer = INVENTORY_FALLBACK_MESSAGE

    # If a prior ticket succeeded, still surface it honestly alongside fallback.
    ticket_raw = state.get("ticket_result")
    if ticket_raw and ticket_raw.get("ok") and ticket_raw.get("tickets"):
        try:
            ticket_out = TicketLookupOutput.model_validate(ticket_raw)
            answer = f"{format_ticket_answer(ticket_out)}\n\n{answer}"
        except Exception:  # noqa: BLE001
            pass

    return {
        "answer": answer,
        "error": None,
        "route": "done",
        "steps": [
            _step(
                state,
                "inventory_fallback",
                "ok",
                started,
                notes=f"inventory fallback reason={error_code} (no invented stock)",
                output={
                    "source": "inventory_fallback",
                    "reason": error_code,
                    "answer": answer,
                    "invented_stock": False,
                    "fallback_message": INVENTORY_FALLBACK_MESSAGE,
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
    inventory_raw = state.get("inventory_result")
    if chunks:
        route = "generate"
    elif inventory_raw and (inventory_raw.get("ok") and inventory_raw.get("products")):
        route = "inventory_answer"
    elif inventory_raw and not inventory_raw.get("ok"):
        route = "inventory_fallback"
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
    """One model call: user-facing ``answer`` + optional ``memory_proposal``.

    Uses ``generate_agent_turn`` (structured JSON). Not a second LLM call or a
    separate memory agent — same generate step with one extra output field.
    """
    started = time.perf_counter()
    chunks = state.get("retrieved") or []
    empty_proposal = MemoryProposal(applicable=False, why="no_retrieved_context")
    if not chunks:
        return {
            "answer": NO_CONTEXT_ANSWER,
            "memory_proposal": empty_proposal.as_dict(),
            "error": None,
            "route": "done",
            "steps": [
                _step(
                    state,
                    "generate",
                    "ok",
                    started,
                    notes="refused generation without retrieved context",
                    output={
                        "answer": NO_CONTEXT_ANSWER,
                        "grounded": False,
                        "source": "rag",
                        "memory_proposal": empty_proposal.as_dict(),
                        "second_model_call": False,
                    },
                )
            ],
        }

    from services.agent.memory.nodes import (
        recalled_records_from_state,
        surface_memory_proposal_in_answer,
    )

    recalled = recalled_records_from_state(state)
    try:
        turn = generate_agent_turn(
            state["question"],
            chunks,
            recalled=recalled,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "answer": None,
            "memory_proposal": MemoryProposal(
                applicable=False, why=f"generation_failed:{type(exc).__name__}"
            ).as_dict(),
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

    answer = turn.answer

    ticket_raw = state.get("ticket_result")
    if ticket_raw:
        try:
            ticket_out = TicketLookupOutput.model_validate(ticket_raw)
            ticket_text = format_ticket_answer(ticket_out)
            answer = f"{answer}\n\nLive ticket data:\n{ticket_text}"
        except Exception:  # noqa: BLE001
            pass

    inventory_raw = state.get("inventory_result")
    if inventory_raw:
        try:
            inv_out = InventoryLookupOutput.model_validate(inventory_raw)
            inv_text = format_inventory_answer(inv_out)
            answer = f"{answer}\n\nLive inventory data:\n{inv_text}"
        except Exception:  # noqa: BLE001
            pass

    # Policy-gate + append "Would you like me to remember…?" at end of user answer.
    # Never writes durable memory on this step.
    answer, proposal = surface_memory_proposal_in_answer(
        answer,
        turn.memory_proposal,
        existing=recalled,
    )

    return {
        "answer": answer,
        "memory_proposal": proposal,
        "error": None,
        "route": "done",
        "steps": [
            _step(
                state,
                "generate",
                "ok",
                started,
                notes=(
                    "structured turn: answer + memory_proposal question to user "
                    "(one model call; no durable write on this step)"
                ),
                output={
                    "answer_len": len(answer or ""),
                    "grounded": True,
                    "source": "rag",
                    "used_ticket": bool(ticket_raw),
                    "used_inventory": bool(inventory_raw),
                    "used_memory": bool(recalled),
                    "memory_hit_count": len(recalled),
                    "memory_via": "MemoryInterface.read→prompt",
                    "memory_proposal": proposal,
                    "proposed_to_user": bool(proposal.get("applicable")),
                    "wrote_to_memory": False,
                    "second_model_call": False,
                    "separate_memory_agent": False,
                    "system_prompt_mutated": False,
                    "full_memory_store_in_prompt": False,
                    "context_sources": [c.get("source_document") for c in chunks],
                },
            )
        ],
    }


def no_context_node(state: AgentState) -> dict[str, Any]:
    """Honest fallback when retrieve returns nothing above the score threshold."""
    started = time.perf_counter()
    no_proposal = MemoryProposal.nothing_to_remember(
        "unknown_answer_must_not_be_learned"
    ).as_dict()
    return {
        "answer": NO_CONTEXT_ANSWER,
        "memory_proposal": no_proposal,
        "error": None,
        "route": "done",
        "steps": [
            _step(
                state,
                "no_context",
                "ok",
                started,
                notes="no chunks above threshold",
                output={
                    "answer": NO_CONTEXT_ANSWER,
                    "source": "rag",
                    "memory_proposal": no_proposal,
                },
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
