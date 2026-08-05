"""Minimal, explicit LangGraph state for the Brasaland support agent.

Course requirement — carry only what a node needs to decide the next step:
question, retrieval result, and (partial) answer. Full conversation history is
intentionally omitted; Part 1 is a single-turn RAG flow.
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
        Final or partial answer produced by ``generate`` / ``no_context``.
    error:
        Machine-readable error code when a node fails (never a stack trace).
    route:
        Explicit routing signal used by conditional edges
        (``empty`` | ``retrieve`` | ``generate`` | ``no_context`` | ``error`` | ``done``).
    steps:
        Append-only per-node trace records (for queryable run logs).
    """

    question: str
    retrieved: list[dict[str, Any]]
    answer: str | None
    error: str | None
    route: str
    steps: Annotated[list[dict[str, Any]], operator.add]
