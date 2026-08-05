"""Brasaland RAG pipeline: retrieve + generate_answer (factored for LangGraph).

External consumers may call ``query()`` for the monolithic path. The LangGraph
agent must call ``retrieve`` and ``generate_answer`` as separate steps so the
flow stays explicit and traceable.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient

from data.process.rag import COLLECTION_NAME, embed, setup

# Re-export indexing helpers so the course contract
# (setup / embed / retrieve / query living under data/pipelines/) is met.
# Implementations of setup + embed stay in data.process.rag to avoid duplication.
__all__ = [
    "COLLECTION_NAME",
    "DEFAULT_K",
    "MIN_SCORE",
    "NO_CONTEXT_ANSWER",
    "embed",
    "generate_answer",
    "query",
    "retrieve",
    "setup",
]

load_dotenv()

GENERATION_MODEL = os.getenv("GENERATION_MODEL_ID", os.getenv("GROQ_MODEL", "gpt-4o-mini"))
DEFAULT_K = 5
MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.40"))
NO_CONTEXT_ANSWER = "There is not enough information available."

SYSTEM_PROMPT = """You are an expert sales and operational assistant for Brasaland.

STRICT BUSINESS RULES (must stay true after LangGraph migration):
1. Base your answer ONLY on the provided Context from the company knowledge base.
2. NEVER say 'zero risk' or '100% safe' for allergen questions. Follow the literal wording in the context.
3. Keep all currency values (USD $, COP $) EXACTLY as they appear in the source text. DO NOT convert currencies.
4. Do NOT invent or estimate any numerical values, weights, percentages, or quantities not present in the context.
5. If the context does not contain enough information, say exactly: "There is not enough information available."
6. Prefer named company entities from CONTEXT (e.g. Lucía Fernández, Felipe Guerrero) when they appear in the context.
"""

qdrant_client = QdrantClient(
    host=os.getenv("QDRANT_HOST", "localhost"),
    port=int(os.getenv("QDRANT_PORT", "6333")),
)


class _LazyGenerationClient:
    """Defer OpenAI construction until first use (imports work without credentials)."""

    def __init__(self) -> None:
        self._client: OpenAI | None = None

    def _get(self) -> OpenAI:
        if self._client is None:
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY") or "test-key"
            base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("GENERATION_BASE_URL")
            self._client = (
                OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
            )
        return self._client

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


# Patchable by unit tests via ``patch("data.pipelines.rag.client", ...)``.
client: Any = _LazyGenerationClient()


def retrieve(query_str: str, k: int = DEFAULT_K, min_score: float = MIN_SCORE) -> list[dict[str, Any]]:
    """Embed the query, search Qdrant, and return payloads that clear ``min_score``."""
    query_vector = embed(query_str)
    search_results = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=k,
    )
    surviving: list[dict[str, Any]] = []
    for hit in search_results:
        if hit.score is None or hit.score < min_score:
            continue
        payload = dict(hit.payload or {})
        payload["_score"] = hit.score
        surviving.append(payload)
    return surviving


def _format_context(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        source = chunk.get("source_document", "unknown")
        text = chunk.get("text", "")
        parts.append(f"--- {source} ---\n{text}")
    return "\n\n".join(parts)


def generate_answer(question: str, context: list[dict[str, Any]] | str) -> str:
    """Generate a grounded answer from *already-retrieved* context.

    This is the generation step factored out of ``query()`` so LangGraph can
    call retrieve and generate as separate nodes. Do not call ``retrieve`` here.
    """
    if isinstance(context, list):
        if not context:
            return NO_CONTEXT_ANSWER
        context_str = _format_context(context)
    else:
        context_str = (context or "").strip()
        if not context_str:
            return NO_CONTEXT_ANSWER

    user_prompt = f"Context:\n{context_str}\n\nQuestion: {question}"
    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content or NO_CONTEXT_ANSWER


def query(
    question: str,
    *,
    chunks: list[dict[str, Any]] | None = None,
) -> str:
    """Monolithic RAG entry for ``POST /knowledge/query``.

    Node contract: LangGraph nodes must **not** call this. They call ``retrieve``
    and ``generate_answer`` separately. If something does reuse ``query()`` with
    already-retrieved context, pass ``chunks=...`` so the internal ``retrieve()``
    is skipped and retrieval is not re-run.
    """
    retrieved_chunks = chunks if chunks is not None else retrieve(question)
    if not retrieved_chunks:
        return NO_CONTEXT_ANSWER
    return generate_answer(question, retrieved_chunks)
