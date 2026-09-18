from __future__ import annotations

import logging
import os

from openai import OpenAI
from qdrant_client import QdrantClient

from data.process.rag import embed, COLLECTION_NAME
from services.safe_errors import ExternalServiceError, call_external

logger = logging.getLogger("brasaland.rag")

GENERATION_MODEL = "gpt-4o-mini"
MIN_SCORE = 0.40

client: OpenAI | None = None
qdrant_client: QdrantClient | None = None


def _llm() -> OpenAI:
    global client
    if client is None:
        try:
            client = OpenAI(timeout=30.0)
        except Exception as error:
            logger.exception("generation client init failed")
            raise ExternalServiceError("language model") from error
    return client


def _qdrant() -> QdrantClient:
    global qdrant_client
    if qdrant_client is None:
        try:
            qdrant_client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", "6333")),
            )
        except Exception as error:
            logger.exception("qdrant client init failed")
            raise ExternalServiceError("vector store") from error
    return qdrant_client


def retrieve(query_str: str, k: int = 3, min_score: float = MIN_SCORE) -> list[dict]:
    query_vector = embed(query_str)
    search_results = call_external(
        "vector store",
        lambda: _qdrant().search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=k,
        ),
    )
    payloads = []
    for hit in search_results:
        if getattr(hit, "score", 0) >= min_score and getattr(hit, "payload", None):
            payloads.append(hit.payload)
    return payloads


def query(question: str) -> str:
    retrieved_chunks = retrieve(question)

    if not retrieved_chunks:
        return "There is not enough information available to answer this question."

    context = "\n\n".join(
        [
            f"--- {chunk.get('source_document', 'document')} ---\n{chunk.get('text', '')}"
            for chunk in retrieved_chunks
        ]
    )

    prompt = f"""
    You are an expert sales and operational assistant for Brasaland. 

    STRICT BUSINESS RULES:
    1. Base your answer ONLY on the provided Context.
    2. NEVER say 'zero risk' or '100% safe' for allergen questions. Follow the literal wording in the context.
    3. Keep all currency values (USD $, COP $) EXACTLY as they appear in the source text. DO NOT convert currencies.
    4. Do NOT invent or estimate any numerical values, weights, percentages, or quantities not present in the context.
    5. If the context does not contain enough information, say: "There is not enough information available."

    Context:
    {context}

    Question: {question}
    """

    response = call_external(
        "language model",
        lambda: _llm().chat.completions.create(
            model=GENERATION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        ),
    )
    try:
        return response.choices[0].message.content or ""
    except (AttributeError, IndexError) as error:
        raise ExternalServiceError("language model") from error
