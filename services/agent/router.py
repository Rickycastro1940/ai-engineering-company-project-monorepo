"""HTTP adapter for the LangGraph support agent — no business logic here."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from services.agent.graph import run_agent
from services.agent.tracing import list_traces, load_trace, query_traces
from services.agent.harness.observability import session_summary, start_guardrail_session

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
def get_traces(
    limit: int = 20,
    node: str | None = None,
    source: str | None = None,
    status: str | None = None,
    question_contains: str | None = None,
) -> list[dict]:
    """List/query recent run traces (newest first).

    Optional filters make the store queryable after the run — e.g.
    ``?source=ticket`` (tool used), ``?source=rag``, ``?node=retrieve``.
    Each trace includes ``sources_order`` / ``source_summary`` showing whether
    the RAG, a tool, or both were used and in what order.
    """
    limit = max(1, min(limit, 100))
    if node or source or status or question_contains:
        return query_traces(
            node=node,
            source=source,
            status=status,
            question_contains=question_contains,
            limit=limit,
        )
    return list_traces(limit=limit)


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str) -> dict:
    """Return a previously saved run trace (queryable after the fact)."""
    try:
        return load_trace(trace_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Trace not found.") from exc


@router.get("/guardrails/summary")
def get_guardrail_summary(all_sessions: bool = False) -> dict:
    """Count guardrail blocks/redirects for the current test session.

    Each event is classified as structural, content, or security.
    Pass ``?all_sessions=true`` to summarize the entire JSONL file.
    """
    if all_sessions:
        from services.agent.harness.audit import get_guardrail_audit
        from services.agent.harness.observability import summarize_events

        payload = summarize_events(get_guardrail_audit().list_entries(limit=100_000))
        payload["session_id"] = "all"
        return payload
    return session_summary()


@router.post("/guardrails/session")
def new_guardrail_session() -> dict:
    """Start a new observability session (resets the in-process session id)."""
    return {"session_id": start_guardrail_session()}
