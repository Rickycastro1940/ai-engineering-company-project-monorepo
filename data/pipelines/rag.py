"""Retrieve and answer from the Brasaland knowledge index.

Canonical query path for ``POST /knowledge/query``. Indexing lives in
``data/process/rag.py`` (collection ``brasaland_kb``).

Default (no API keys):

- retrieval uses local hashed embeddings plus token overlap
- the answer is an extractive quote of the cited chunks

Live generation and Qdrant are opt-in:

- ``BRASALAND_RAG_LLM=openai`` and ``OPENAI_API_KEY`` — chat completion
- ``BRASALAND_RAG_BACKEND=qdrant`` — hybrid search on ``brasaland_kb``
  (dense cosine + BM25 sparse, fused with reciprocal rank fusion)

After retrieval, a cross-encoder re-ranks the shortlist. ``COHERE_API_KEY``
calls Cohere Rerank. With no key, a local pairwise scorer runs instead so
location-manager questions still return an answer.
"""
from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from data.process.rag import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    content_tokens,
    embed,
    embed_local,
    local_index,
    match_blob,
    qdrant_client,
    rag_backend,
    sparse_term_vector,
    tokens,
)
from services.safe_errors import ExternalServiceError, call_external

MIN_SCORE_LOCAL = 0.30
MIN_SCORE_QDRANT = 0.40
# Reciprocal-rank fusion scores are much smaller than cosine. Below this
# ceiling, scores are scaled so the best fused hit is 1.0 and the cosine
# floor still applies.
FUSION_SCORE_CEILING = 0.2
DEFAULT_K = 5
RERANK_POOL = 4
COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"
COHERE_RERANK_MODEL = "rerank-v3.5"
INSUFFICIENT = "There is not enough information available to answer this question."

SYSTEM_RULES = """You are the Brasaland knowledge assistant for restaurant staff and leadership.

STRICT BUSINESS RULES:
1. Base your answer ONLY on the provided Context.
2. NEVER say 'zero risk' or '100% safe' for allergen questions. Follow the literal wording in the context.
3. Keep all currency values (USD and COP) EXACTLY as they appear in the source text. DO NOT convert currencies.
4. Do NOT invent or estimate any numerical values, weights, percentages, or quantities not present in the context.
5. If the context does not contain enough information, say: "There is not enough information available to answer this question."
6. Brasa Points runs on physical stamp cards unless the context explicitly says a digital app is available today.
7. Cite the source document name in the answer.
"""


def llm_backend() -> str:
    return os.getenv("BRASALAND_RAG_LLM", "extractive").strip().lower() or "extractive"


def _token_matches(query_token: str, chunk_tokens: set[str]) -> bool:
    if query_token in chunk_tokens:
        return True
    if len(query_token) < 4:
        return False
    for chunk_token in chunk_tokens:
        if len(chunk_token) < 4:
            continue
        if query_token.startswith(chunk_token) or chunk_token.startswith(query_token):
            return True
    return False


def token_recall(question: str, text: str) -> float:
    query_tokens = content_tokens(question)
    if not query_tokens:
        return 0.0
    chunk_tokens = set(tokens(text))
    hits = sum(1 for token in query_tokens if _token_matches(token, chunk_tokens))
    return hits / len(query_tokens)


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def hybrid_score(question: str, chunk: dict, query_vector: list[float]) -> float:
    lexical = token_recall(question, match_blob(chunk))
    cosine = max(0.0, _dot(query_vector, chunk["vector"]))
    return (0.75 * lexical) + (0.25 * cosine)


def _squash(value: float) -> float:
    if value <= 0.0:
        return 0.0
    return value / (1.0 + value)


def bm25_lite(question: str, text: str, k1: float = 1.2, b: float = 0.75, avgdl: float = 80.0) -> float:
    """Okapi BM25 without a corpus IDF table, squashed to 0..1.

    Qdrant applies IDF itself (``Modifier.IDF``). This scorer is the local
    keyword half of the cross-encoder, for machines with no Cohere key.
    """
    query_tokens = list(dict.fromkeys(content_tokens(question)))
    if not query_tokens:
        return 0.0
    document_tokens = tokens(text)
    if not document_tokens:
        return 0.0
    frequencies: dict[str, int] = {}
    for token in document_tokens:
        frequencies[token] = frequencies.get(token, 0) + 1
    length_norm = 1.0 - b + b * (len(document_tokens) / avgdl)
    total = 0.0
    for token in query_tokens:
        frequency = frequencies.get(token, 0)
        if frequency == 0 and len(token) >= 4:
            frequency = sum(
                count
                for word, count in frequencies.items()
                if len(word) >= 4 and (token.startswith(word) or word.startswith(token))
            )
        if frequency <= 0:
            continue
        numerator = frequency * (k1 + 1.0)
        denominator = frequency + k1 * length_norm
        total += numerator / denominator
    return _squash(total / len(query_tokens))


def _ordered_coverage(question: str, text: str) -> float:
    query_tokens = content_tokens(question)
    document_tokens = tokens(text)
    if not query_tokens or not document_tokens:
        return 0.0
    cursor = 0
    found = 0
    for token in query_tokens:
        while cursor < len(document_tokens) and not _token_matches(token, {document_tokens[cursor]}):
            cursor += 1
        if cursor >= len(document_tokens):
            break
        found += 1
        cursor += 1
    return found / len(query_tokens)


def _rerank_text(chunk: dict) -> str:
    if chunk.get("source_document"):
        return match_blob(chunk)
    return str(chunk.get("text") or "")


def local_cross_encoder_score(question: str, chunk: dict, query_vector: list[float] | None = None) -> float:
    """Pairwise score for one (question, chunk). No network and no model file.

    A bi-encoder compares two vectors computed apart. This reads the question
    and the chunk together: token overlap, in-order coverage, and BM25.
    Dense cosine is added only when the chunk already carries a vector.
    """
    text = _rerank_text(chunk)
    lexical = token_recall(question, text)
    coverage = _ordered_coverage(question, text)
    keyword = bm25_lite(question, text)
    cosine = 0.0
    vector = chunk.get("vector")
    if query_vector and vector:
        cosine = max(0.0, _dot(query_vector, vector))
    interaction = lexical * (0.5 + 0.5 * coverage)
    score = (0.40 * interaction) + (0.25 * lexical) + (0.20 * keyword) + (0.15 * cosine)
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def rerank_backend() -> str:
    """``cohere`` only when a key is present. Otherwise the local scorer."""
    forced = os.getenv("BRASALAND_RAG_RERANK", "").strip().lower()
    has_key = bool(os.getenv("COHERE_API_KEY", "").strip())
    if forced == "local":
        return "local"
    if forced == "cohere":
        return "cohere" if has_key else "local"
    return "cohere" if has_key else "local"


def _rerank_local(
    question: str,
    pairs: list[tuple[float, dict]],
    query_vector: list[float] | None,
) -> list[tuple[float, dict]]:
    scored: list[tuple[float, dict]] = []
    for retrieval_score, chunk in pairs:
        cross = local_cross_encoder_score(question, chunk, query_vector)
        blended = (0.65 * cross) + (0.35 * max(0.0, min(1.0, float(retrieval_score))))
        scored.append((blended, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _cohere_rerank_scores(question: str, documents: list[str]) -> list[tuple[int, float]]:
    """Call Cohere Rerank. The key stays in the Authorization header."""
    api_key = os.getenv("COHERE_API_KEY", "").strip()
    if not api_key:
        raise ExternalServiceError("reranker")
    url = os.getenv("COHERE_RERANK_URL", COHERE_RERANK_URL).strip() or COHERE_RERANK_URL
    model = os.getenv("COHERE_RERANK_MODEL", COHERE_RERANK_MODEL).strip() or COHERE_RERANK_MODEL
    body = json.dumps(
        {
            "model": model,
            "query": question,
            "documents": [document[:4000] for document in documents],
            "top_n": len(documents),
        }
    ).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    def _run():
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    payload = call_external("reranker", _run)
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ExternalServiceError("reranker")
    ranked: list[tuple[int, float]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if isinstance(index, int) and 0 <= index < len(documents) and isinstance(score, (int, float)):
            ranked.append((index, float(score)))
    if not ranked:
        raise ExternalServiceError("reranker")
    return ranked


def _rerank_cohere(question: str, pairs: list[tuple[float, dict]]) -> list[tuple[float, dict]]:
    documents = [str(chunk.get("text") or "") for _, chunk in pairs]
    ordered = _cohere_rerank_scores(question, documents)
    seen: set[int] = set()
    scored: list[tuple[float, dict]] = []
    for index, score in ordered:
        if index in seen:
            continue
        seen.add(index)
        scored.append((float(score), pairs[index][1]))
    for index, (retrieval_score, chunk) in enumerate(pairs):
        if index not in seen:
            scored.append((float(retrieval_score), chunk))
    return scored


def rerank_pairs(
    question: str,
    pairs: list[tuple[float, dict]],
    query_vector: list[float] | None = None,
) -> list[tuple[float, dict]]:
    """Re-rank ``(retrieval_score, chunk)`` pairs. No Cohere call without a key."""
    if not pairs:
        return []
    if rerank_backend() == "cohere":
        return _rerank_cohere(question, pairs)
    return _rerank_local(question, pairs, query_vector)


def _public(chunk: dict, score: float) -> dict:
    return {
        "source_document": chunk.get("source_document", ""),
        "section": chunk.get("section", ""),
        "text": chunk.get("text", ""),
        "score": round(float(score), 4),
        "chunk_index": int(chunk.get("chunk_index", 0)),
        "language": chunk.get("language", "en"),
    }


def _point_list(response) -> list:
    if hasattr(response, "points"):
        return list(response.points)
    return list(response)


def _collection_has_sparse(client) -> bool:
    info = client.get_collection(collection_name=COLLECTION_NAME)
    params = getattr(getattr(info, "config", None), "params", None)
    sparse = getattr(params, "sparse_vectors", None)
    if isinstance(sparse, dict):
        return SPARSE_VECTOR_NAME in sparse
    return bool(getattr(sparse, SPARSE_VECTOR_NAME, None))


def _qdrant_models():
    from qdrant_client import models

    return models


def _hybrid_points(client, vector: list[float], indices: list[int], values: list[float], k: int) -> list:
    """Dense prefetch + BM25 sparse prefetch, fused with reciprocal rank fusion."""
    models = _qdrant_models()
    response = client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            models.Prefetch(query=vector, using=DENSE_VECTOR_NAME, limit=k),
            models.Prefetch(
                query=models.SparseVector(indices=indices, values=values),
                using=SPARSE_VECTOR_NAME,
                limit=k,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k,
        with_payload=True,
    )
    return _point_list(response)


def _dense_points(client, vector: list[float], k: int) -> list:
    """Single dense query. Used for collections indexed before named sparse vectors."""
    if hasattr(client, "query_points"):
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=k,
            with_payload=True,
        )
        return _point_list(response)
    if hasattr(client, "search"):
        return list(
            client.search(
                collection_name=COLLECTION_NAME,
                query_vector=vector,
                limit=k,
            )
        )
    raise ExternalServiceError("vector store")


def _scale_fusion_scores(pairs: list[tuple[float, dict]]) -> list[tuple[float, dict]]:
    """Keep cosine scores as-is. Scale tiny RRF scores so the top hit is 1.0."""
    if not pairs:
        return []
    top = max(score for score, _payload in pairs)
    if top <= 0.0:
        return []
    if top < FUSION_SCORE_CEILING:
        return [(score / top, payload) for score, payload in pairs if score > 0.0]
    return [(score, payload) for score, payload in pairs if score > 0.0]


def search_qdrant(
    vector: list[float],
    k: int,
    query_text: str | None = None,
) -> list[tuple[float, dict]]:
    """Hybrid ``(score, payload)`` hits from ``brasaland_kb``.

    When the collection has a ``bm25`` sparse vector and ``query_text`` has
    keywords, dense and sparse lists are fused. An older dense-only collection
    is searched with cosine alone. Fusion scores are scaled onto 0..1.
    """

    def _run():
        client = qdrant_client()
        indices, values = sparse_term_vector(query_text or "")
        use_hybrid = bool(query_text and indices and _collection_has_sparse(client))
        if use_hybrid:
            try:
                hits = _hybrid_points(client, vector, indices, values, k)
            except AttributeError:
                hits = _dense_points(client, vector, k)
        else:
            hits = _dense_points(client, vector, k)
        pairs: list[tuple[float, dict]] = []
        for hit in hits:
            payload = dict(getattr(hit, "payload", None) or {})
            pairs.append((float(getattr(hit, "score", 0.0) or 0.0), payload))
        return _scale_fusion_scores(pairs)

    return call_external("vector store", _run)


def retrieve(query_str: str, k: int = DEFAULT_K, min_score: float | None = None) -> list[dict]:
    """Top chunks for ``query_str``.

    Local mode ranks with token overlap plus cosine, then the cross-encoder
    reorders that shortlist. Qdrant mode fuses dense and BM25 sparse hits,
    drops scores under the floor, then re-ranks.
    """
    if rag_backend() == "qdrant":
        floor = MIN_SCORE_QDRANT if min_score is None else min_score
        vector = embed(query_str)
        pool: list[tuple[float, dict]] = []
        for score, payload in search_qdrant(vector, max(k * RERANK_POOL, k), query_str):
            if score < floor or not payload.get("text"):
                continue
            pool.append((score, payload))
        ranked = rerank_pairs(query_str, pool, vector)
        return [_public(payload, score) for score, payload in ranked[:k]]

    floor = MIN_SCORE_LOCAL if min_score is None else min_score
    query_vector = embed_local(query_str)
    ranked: list[tuple[float, dict]] = []
    for chunk in local_index():
        score = hybrid_score(query_str, chunk, query_vector)
        if score >= floor:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    shortlist = ranked[:k]
    ordered = rerank_pairs(query_str, shortlist, query_vector)
    return [_public(chunk, score) for score, chunk in ordered]


def build_prompt(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join(
        f"--- {chunk.get('source_document', 'document')} / {chunk.get('section', '')} ---\n{chunk.get('text', '')}"
        for chunk in chunks
    )
    return (
        f"{SYSTEM_RULES}\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n"
    )


def extractive_answer(chunks: list[dict]) -> str:
    if not chunks:
        return INSUFFICIENT
    blocks = [
        f"Source: {chunk['source_document']} ({chunk['section']})\n{chunk['text']}"
        for chunk in chunks
    ]
    return "\n\n".join(blocks)


def generate_openai(question: str, chunks: list[dict]) -> str:
    """One chat completion. Caller must set ``BRASALAND_RAG_LLM=openai``."""
    from data.process.rag import _openai

    prompt = build_prompt(question, chunks)
    model = os.getenv("BRASALAND_RAG_LLM_MODEL", "gpt-4o-mini")

    def _run():
        # Reuse the embeddings client factory; a missing key raises ExternalServiceError
        # with service name "embeddings". Map that to the language model for this call.
        try:
            client = _openai()
        except ExternalServiceError as error:
            raise ExternalServiceError("language model") from error
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        content = response.choices[0].message.content
        return content or ""

    return call_external("language model", _run)


def _text_deltas(text: str, size: int = 24):
    """Small slices of a finished extractive answer, same grain as LLM tokens."""
    cleaned = text or ""
    if not cleaned:
        return
    for start in range(0, len(cleaned), size):
        yield cleaned[start : start + size]


def iter_openai_deltas(question: str, chunks: list[dict]):
    """OpenAI chat deltas. Each item is ``choices[0].delta.content``."""
    from data.process.rag import _openai

    prompt = build_prompt(question, chunks)
    model = os.getenv("BRASALAND_RAG_LLM_MODEL", "gpt-4o-mini")

    def _open():
        try:
            client = _openai()
        except ExternalServiceError as error:
            raise ExternalServiceError("language model") from error
        return client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            stream=True,
        )

    stream = call_external("language model", _open)
    try:
        for event in stream:
            choices = getattr(event, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0].delta, "content", None)
            if delta:
                yield delta
    finally:
        closer = getattr(stream, "close", None)
        if closer:
            closer()


def query_stream(question: str, k: int = DEFAULT_K):
    """Yield answer text as it is produced.

    This assistant is retrieval plus a completion, not a LangGraph graph.
    LangGraph ``stream_mode="messages"`` is the mode that yields LLM tokens.
    ``values`` and ``updates`` emit a whole node state, which is too coarse
    for a token UI, so they are not used. Each yield here is one text delta.
    """
    cleaned = (question or "").strip()
    if not cleaned:
        yield from _text_deltas(INSUFFICIENT)
        return
    sources = retrieve(cleaned, k=k)
    if not sources:
        yield from _text_deltas(INSUFFICIENT)
        return
    if llm_backend() == "openai":
        produced = False
        for delta in iter_openai_deltas(cleaned, sources):
            produced = True
            yield delta
        if produced:
            return
    yield from _text_deltas(extractive_answer(sources))


def answer_question(question: str, k: int = DEFAULT_K) -> dict:
    """Grounded answer plus the source chunks that support it."""
    cleaned = (question or "").strip()
    if not cleaned:
        return {"answer": INSUFFICIENT, "sources": []}
    sources = retrieve(cleaned, k=k)
    if not sources:
        return {"answer": INSUFFICIENT, "sources": []}
    if llm_backend() == "openai":
        generated = generate_openai(cleaned, sources).strip()
        answer = generated or extractive_answer(sources)
    else:
        answer = extractive_answer(sources)
    return {"answer": answer, "sources": sources}


def query(question: str) -> str:
    """Answer text only. Prefer ``answer_question`` when citations are required."""
    return answer_question(question)["answer"]
