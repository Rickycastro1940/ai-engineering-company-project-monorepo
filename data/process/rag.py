from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from services.safe_errors import ExternalServiceError, call_external

load_dotenv()

logger = logging.getLogger("brasaland.embeddings")

COLLECTION_NAME = "brasaland_kb"
EMBEDDING_MODEL = "text-embedding-3-small"

client: OpenAI | None = None
qdrant_client: QdrantClient | None = None


def _openai_client() -> OpenAI:
    global client
    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ExternalServiceError("embeddings")
        base_url = os.getenv("OPENAI_BASE_URL")
        try:
            client = (
                OpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
                if base_url
                else OpenAI(api_key=api_key, timeout=30.0)
            )
        except Exception as error:
            logger.exception("openai client init failed")
            raise ExternalServiceError("embeddings") from error
    return client


def _qdrant() -> QdrantClient:
    global qdrant_client
    if qdrant_client is None:
        try:
            port = int(os.getenv("QDRANT_PORT", "6333"))
            qdrant_client = QdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=port,
            )
        except Exception as error:
            logger.exception("qdrant client init failed")
            raise ExternalServiceError("vector store") from error
    return qdrant_client


def embed(text: str) -> list[float]:
    response = call_external(
        "embeddings",
        lambda: _openai_client().embeddings.create(input=text, model=EMBEDDING_MODEL),
    )
    try:
        return response.data[0].embedding
    except (AttributeError, IndexError, KeyError) as error:
        raise ExternalServiceError("embeddings") from error


def setup(docs_dir: str = "docs/company-knowledge-base/"):
    store = _qdrant()

    def _ensure_collection() -> None:
        if store.collection_exists(collection_name=COLLECTION_NAME):
            store.delete_collection(collection_name=COLLECTION_NAME)
        store.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )

    call_external("vector store", _ensure_collection)

    points = []
    doc_paths = list(Path(docs_dir).rglob("*.md")) if Path(docs_dir).exists() else list(Path(".").rglob("*.en.md"))

    for filepath in doc_paths:
        try:
            content = filepath.read_text(encoding="utf-8")
        except OSError:
            logger.warning("skipped unreadable document")
            continue
        chunks = [c.strip() for c in content.split("\n\n") if len(c.strip()) > 50]
        doc_name = filepath.name.replace("brasaland-", "").replace(".en.md", "")

        for idx, chunk in enumerate(chunks):
            vector = embed(chunk)
            payload = {
                "company": "brasaland",
                "source_document": doc_name,
                "section": f"Chunk {idx+1}",
                "language": "en",
                "chunk_index": idx,
                "text": chunk
            }
            points.append(PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload))

    if points:
        call_external(
            "vector store",
            lambda: store.upsert(collection_name=COLLECTION_NAME, points=points),
        )
        print(f"Successfully indexed {len(points)} chunks into '{COLLECTION_NAME}'.")
    else:
        print("No documents found. Please verify the document path.")


if __name__ == "__main__":
    try:
        setup()
    except ExternalServiceError:
        raise SystemExit(1)
