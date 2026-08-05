"""Brasaland knowledge-base query API (see CONTEXT.md).

POST /knowledge/query — request ``{"question": "..."}``, response ``{"answer": "..."}``.

Thin HTTP adapter only: validates the request and delegates to
``data.pipelines.rag.query()``. Retrieval, embedding, and generation live in
``data/pipelines/`` — never duplicated here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from data.pipelines.rag import query

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)


class QueryResponse(BaseModel):
    """Public API shape — answer string only; never chunks, scores, or Qdrant payloads."""

    model_config = ConfigDict(extra="forbid")

    answer: str


@router.post("/query", response_model=QueryResponse)
def query_knowledge_base(payload: QueryRequest) -> QueryResponse:
    """Return the model-generated answer only."""
    try:
        answer_text = query(payload.question.strip())
        return QueryResponse(answer=answer_text)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process knowledge query: {error}",
        ) from error
