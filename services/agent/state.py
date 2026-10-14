"""Minimal state for the Brasaland support graph.

Nodes need the current question, the chunks ``retrieve`` already returned,
the answer, a short error, and the steps of this run. Prior turns are not
stored here: each ``POST /agent/query`` is one question.
"""
from __future__ import annotations

import operator
from typing import Annotated, Optional, Sequence, TypedDict


class AgentState(TypedDict):
    question: str
    retrieved_context: Optional[list]
    answer: Optional[str]
    trace_steps: Annotated[Sequence[dict], operator.add]
    error: Optional[str]
