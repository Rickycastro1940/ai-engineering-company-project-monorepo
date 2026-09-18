import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from data.pipelines.rag import query
from services.safe_errors import ExternalServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_QUERY_IO_ERRORS: tuple[type[BaseException], ...] = (OSError, TimeoutError, ConnectionError)
try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError

    _QUERY_IO_ERRORS = (*_QUERY_IO_ERRORS, APIConnectionError, APITimeoutError, APIStatusError)
except ImportError:
    pass
try:
    from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

    _QUERY_IO_ERRORS = (*_QUERY_IO_ERRORS, UnexpectedResponse, ResponseHandlingException)
except ImportError:
    pass


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
    except ExternalServiceError as error:
        logger.exception("knowledge query transport failed")
        raise HTTPException(
            status_code=503,
            detail="The knowledge assistant is unavailable. Try again in a moment.",
        ) from error
    except _QUERY_IO_ERRORS as error:
        logger.exception("knowledge query transport failed")
        raise HTTPException(
            status_code=503,
            detail="The knowledge assistant is unavailable. Try again in a moment.",
        ) from error

    return QueryResponse(answer=answer_text or "")
