"""Minimal, explicit LangGraph state for the Brasaland support agent.

Course requirement — carry only what a node needs to decide the next step:
question, retrieval result, ticket tool I/O, and (partial) answer. Full
conversation history is intentionally omitted.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    """Shared graph state — minimal and explicit.

    Fields
    ------
    question:
        User question for this run (normalized by ``receive_question``).
    retrieved:
        Chunks returned by ``data.pipelines.rag.retrieve`` (may be empty).
    answer:
        Final or partial answer produced by generate / ticket / fallback nodes.
    error:
        Machine-readable error code when a node fails (never a stack trace).
    route:
        Explicit routing signal used by conditional edges
        (``empty`` | ``retrieve`` | ``ticket`` | ``both`` | ``generate`` |
        ``no_context`` | ``ticket_answer`` | ``ticket_fallback`` | ``error`` |
        ``done``).
    needs_ticket / needs_rag:
        Source flags set by ``receive_question`` for conditional edges / traces.
    ticket_query:
        Serialized ``TicketLookupInput`` when the ticket tool should run.
    ticket_result:
        Serialized ``TicketLookupOutput`` from the ticket tool node.
    sources_used:
        Ordered list of sources that ran (``ticket`` / ``rag``) for traces.
    steps:
        Append-only per-node trace records (for queryable run logs).
    """

    question: str
    retrieved: list[dict[str, Any]]
    answer: str | None
    error: str | None
    route: str
    needs_ticket: bool
    needs_rag: bool
    ticket_query: dict[str, Any] | None
    ticket_result: dict[str, Any] | None
    sources_used: Annotated[list[str], operator.add]
    steps: Annotated[list[dict[str, Any]], operator.add]
