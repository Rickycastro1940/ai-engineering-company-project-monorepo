"""Minimal, explicit LangGraph state for the Brasaland support agent.

Deliberately omits full conversation history — Part 1 only needs the current
question, retrieval result, answer, and routing metadata for one run.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    """Shared state passed between nodes."""

    question: str
    retrieved: list[dict[str, Any]]
    answer: str | None
    error: str | None
    route: str
    # Append-only step log used for the queryable run trace.
    steps: Annotated[list[dict[str, Any]], operator.add]
