from __future__ import annotations

import os

from openai import OpenAI
from qdrant_client import QdrantClient

from data.process.rag import embed
from services.safe_errors import ExternalServiceError, call_external

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
COLLECTION_NAME = "company_knowledge_base"
DEFAULT_MIN_SCORE = 0.70
GENERATION_MODEL_ID = "gpt-4o-mini"

qdrant_client: QdrantClient | None = None
llm_client: OpenAI | None = None


def _qdrant() -> QdrantClient:
    global qdrant_client
    if qdrant_client is None:
        try:
            qdrant_client = QdrantClient(
                host=QDRANT_HOST,
                port=int(os.getenv("QDRANT_PORT", "6333")),
            )
        except Exception as error:
            raise ExternalServiceError("vector store") from error
    return qdrant_client


def _llm() -> OpenAI:
    global llm_client
    if llm_client is None:
        try:
            llm_client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                timeout=30.0,
            )
        except Exception as error:
            raise ExternalServiceError("language model") from error
    return llm_client


def retrieve(
    query: str, *, k: int = 5, min_score: float = DEFAULT_MIN_SCORE
) -> list[dict]:
    query_vector = embed(query)
    search_results = call_external(
        "vector store",
        lambda: _qdrant().search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=k,
        ),
    )

    surviving_payloads = []
    for hit in search_results:
        if getattr(hit, "score", 0) >= min_score:
            payload = hit.payload or {}
            payload["_score"] = hit.score
            surviving_payloads.append(payload)

    return surviving_payloads


def query(question: str) -> str:
    chunks = retrieve(question, k=5, min_score=DEFAULT_MIN_SCORE)

    if not chunks:
        context_str = "No relevant documents found in the internal knowledge base."
    else:
        context_str = "\n\n---\n\n".join([chunk.get("text", "") for chunk in chunks])

    system_prompt = (
        "You are an expert sales assistant helping the commercial team answer prospect and client questions. "
        "Answer the question accurately using ONLY the provided internal document context. "
        "Adopt a professional, helpful salesperson's perspective with the voice and priorities of the business. "
        "If the context does not contain enough information to answer, state clearly that you do not have that information."
    )
    user_prompt = f"Context:\n{context_str}\n\nQuestion: {question}"

    response = call_external(
        "language model",
        lambda: _llm().chat.completions.create(
            model=GENERATION_MODEL_ID,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        ),
    )
    try:
        return response.choices[0].message.content
    except (AttributeError, IndexError) as error:
        raise ExternalServiceError("language model") from error
