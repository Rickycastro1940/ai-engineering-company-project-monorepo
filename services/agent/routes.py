"""POST /agent/query — invoke the compiled support graph and return its answer.

The route does not retrieve or generate. Those steps live in the graph nodes,
which call ``data/pipelines/rag.py``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from typing import Optional

from pydantic import BaseModel, Field

from services.agent.graph import AgentGraphError, run_agent
from services.agent.tracing import get_trace

logger = logging.getLogger("brasaland.agent")

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    question: str = Field(..., max_length=2000)


class AgentQueryResponse(BaseModel):
    answer: str
    trace_id: str


class AgentTraceResponse(BaseModel):
    trace_id: str
    question: str
    answer: Optional[str] = None
    error: Optional[str] = None
    trace_steps: list
    nodes: list
    checkpoint_id: Optional[str] = None


@router.post("/query", response_model=AgentQueryResponse)
def query_agent(payload: AgentQueryRequest) -> AgentQueryResponse:
    """Run one question through the compiled graph."""
    try:
        result = run_agent(payload.question)
    except AgentGraphError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Agent failed. Check trace {error.trace_id}.",
        ) from error

    error_text = result.get("error")
    if error_text:
        status = 400 if "empty" in str(error_text).lower() else 503
        raise HTTPException(status_code=status, detail=str(error_text))

    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(
            status_code=503,
            detail=f"Agent failed. Check trace {result['trace_id']}.",
        )
    logger.info("agent_query trace_id=%s nodes=%s", result["trace_id"], result.get("nodes"))
    return AgentQueryResponse(answer=answer, trace_id=result["trace_id"])


@router.get("/traces/{trace_id}", response_model=AgentTraceResponse)
def read_trace(trace_id: str) -> AgentTraceResponse:
    """Return the stored trace for a finished run."""
    found = get_trace(trace_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Trace was not found.")
    return AgentTraceResponse(**found)
