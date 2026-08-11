"""Minimal, explicit LangGraph state for the Brasaland support agent.

Course requirement — carry only what a node needs to decide the next step:
question, retrieval result, tool I/O, and (partial) answer. Full conversation
history is intentionally omitted.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    """Shared graph state — minimal and explicit."""

    question: str
    retrieved: list[dict[str, Any]]
    answer: str | None
    error: str | None
    route: str
    needs_ticket: bool
    needs_inventory: bool
    needs_rag: bool
    ticket_query: dict[str, Any] | None
    ticket_result: dict[str, Any] | None
    inventory_query: dict[str, Any] | None
    inventory_result: dict[str, Any] | None
    # Durable semantic memory (extends MCP + RAG — does not replace them).
    memory_hits: list[dict[str, Any]]
    memory_writes: list[dict[str, Any]]
    # From the same generate call (structured field) — not a second LLM call.
    # When applicable, also surfaced as a question inside ``answer`` (no write yet).
    memory_proposal: dict[str, Any] | None
    memory_pending_proposal: dict[str, Any] | None
    # Post-interaction self-eval decisions derived from memory_proposal.
    memory_self_evaluations: list[dict[str, Any]]
    sources_used: Annotated[list[str], operator.add]
    steps: Annotated[list[dict[str, Any]], operator.add]
