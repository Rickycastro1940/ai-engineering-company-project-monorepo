import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from data.pipelines.rag import query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str


@router.post("/query", response_model=QueryResponse)
async def query_knowledge_base(payload: QueryRequest):
    """
    Accepts a question, delegates to data.pipelines.rag.query(),
    and returns only the model-generated answer string.
    """
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        answer_text = query(payload.question)
        return QueryResponse(answer=answer_text)
    except Exception:
        logger.exception("knowledge query failed")
        raise HTTPException(status_code=500, detail="Failed to process knowledge query.")