"""HTTP adapter for the LangGraph support agent — no business logic here."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from services.agent.graph import run_agent
from services.agent.tracing import list_traces, load_trace

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    question: str = Field(default="", description="User question for the support agent")


class AgentQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str | None
    trace_id: str
    status: str
    error: str | None = None


@router.post("/query", response_model=AgentQueryResponse)
def agent_query(payload: AgentQueryRequest) -> AgentQueryResponse:
    """Invoke the compiled LangGraph agent and return answer + trace id.

    Business logic (retrieve / generate) lives in the graph nodes, not here.
    """
    result = run_agent(payload.question)
    if result["status"] == "error" and result.get("error") == "Question cannot be empty.":
        raise HTTPException(status_code=400, detail=result["error"])
    if result["status"] == "error":
        raise HTTPException(
            status_code=500,
            detail=result.get("error") or "The agent failed while processing the question.",
        )
    return AgentQueryResponse(
        answer=result.get("answer"),
        trace_id=result["trace_id"],
        status=result["status"],
        error=None,
    )


@router.get("/traces")
def get_traces(limit: int = 20) -> list[dict]:
    """List recent queryable run traces (newest first)."""
    return list_traces(limit=max(1, min(limit, 100)))


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    """Return a previously saved run trace (queryable after the fact)."""
    try:
        return load_trace(trace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Trace not found.") from exc
