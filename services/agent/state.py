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
    sources_used: Annotated[list[str], operator.add]
    steps: Annotated[list[dict[str, Any]], operator.add]
