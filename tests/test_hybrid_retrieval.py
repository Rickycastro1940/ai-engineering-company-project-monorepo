"""Hybrid Qdrant retrieval and cross-encoder re-rank. No live Qdrant or Cohere."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


ALLERGEN = {
    "source_document": "brasaland-menu-allergens.en.md",
    "section": "Menu Allergen Guide · part 1",
    "text": "House Sauce contains soy and sulfites. Staff must not call it zero risk.",
    "chunk_index": 1,
    "language": "en",
}
WASTE = {
    "source_document": "brasaland-waste-protocol.en.md",
    "section": "Waste · part 3",
    "text": "Cardboard boxes are broken down for recycling after the dinner service.",
    "chunk_index": 2,
    "language": "en",
}


def _payload_point(score: float, payload: dict):
    return SimpleNamespace(score=score, payload=dict(payload))


class _Models:
    class Fusion:
        RRF = "rrf"

    class FusionQuery:
        def __init__(self, fusion):
            self.fusion = fusion

    class Prefetch:
        def __init__(self, query, using, limit):
            self.query = query
            self.using = using
            self.limit = limit

    class SparseVector:
        def __init__(self, indices, values):
            self.indices = list(indices)
            self.values = list(values)


def _sparse_collection():
    return SimpleNamespace(
        config=SimpleNamespace(params=SimpleNamespace(sparse_vectors={"bm25": object()}))
    )


def _dense_collection():
    return SimpleNamespace(
        config=SimpleNamespace(params=SimpleNamespace(sparse_vectors=None))
    )


def test_sparse_term_vector_is_stable_and_counts_repeats():
    process = __import__("data.process.rag", fromlist=["sparse_term_vector", "merge_sparse"])
    first = process.sparse_term_vector("house sauce soy")
    second = process.sparse_term_vector("house sauce soy")
    assert first == second
    assert first[0]
    assert len(first[0]) == len(first[1])
    once = dict(zip(*process.sparse_term_vector("soy")))
    twice = dict(zip(*process.sparse_term_vector("soy soy")))
    assert len(once) == 1
    index = next(iter(once))
    assert once[index] == 1.0
    assert twice[index] == 2.0
    merged_index, merged_value = process.merge_sparse([3, 3, 1], [0.5, 0.5, 1.0])
    assert merged_index == [1, 3]
    assert merged_value == [1.0, 1.0]


def test_local_cross_encoder_prefers_allergen_chunk():
    pipelines = __import__("data.pipelines.rag", fromlist=["local_cross_encoder_score"])
    question = "What does the House Sauce contain?"
    allergen = pipelines.local_cross_encoder_score(question, ALLERGEN, None)
    waste = pipelines.local_cross_encoder_score(question, WASTE, None)
    assert allergen > waste
    assert allergen > 0.5
    assert waste < 0.2


def test_missing_cohere_key_reranks_locally(monkeypatch):
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv("BRASALAND_RAG_RERANK", raising=False)
    pipelines = __import__("data.pipelines.rag", fromlist=["rerank_backend", "rerank_pairs", "urlopen"])

    def _boom(*_args, **_kwargs):
        raise AssertionError("Cohere was called without a key")

    monkeypatch.setattr(pipelines, "urlopen", _boom)
    assert pipelines.rerank_backend() == "local"
    monkeypatch.setenv("BRASALAND_RAG_RERANK", "cohere")
    assert pipelines.rerank_backend() == "local"
    ranked = pipelines.rerank_pairs(
        "House Sauce soy sulfites",
        [(0.95, dict(WASTE)), (0.55, dict(ALLERGEN))],
        None,
    )
    assert ranked[0][1]["source_document"] == ALLERGEN["source_document"]
    assert ranked[0][0] > ranked[1][0]
    assert "cohere" not in json.dumps(ranked[0][1]).lower()


def test_cohere_rerank_reorders_and_keeps_key_out_of_hits(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "cohere-test-key-not-real")
    monkeypatch.delenv("BRASALAND_RAG_RERANK", raising=False)
    pipelines = __import__("data.pipelines.rag", fromlist=["rerank_backend", "rerank_pairs"])
    assert pipelines.rerank_backend() == "cohere"
    captured = {}

    class _Body:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "results": [
                        {"index": 1, "relevance_score": 0.93},
                        {"index": 0, "relevance_score": 0.11},
                    ]
                }
            ).encode("utf-8")

    def _urlopen(request, timeout=0):
        captured["timeout"] = timeout
        captured["auth"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Body()

    monkeypatch.setattr(pipelines, "urlopen", _urlopen)
    ranked = pipelines.rerank_pairs(
        "House Sauce soy",
        [(0.8, dict(WASTE)), (0.4, dict(ALLERGEN))],
        None,
    )
    assert captured["body"]["model"] == "rerank-v3.5"
    assert captured["body"]["documents"][1].startswith("House Sauce")
    assert captured["auth"] == "Bearer cohere-test-key-not-real"
    assert ranked[0][1]["source_document"] == ALLERGEN["source_document"]
    assert ranked[0][0] == pytest.approx(0.93)
    dumped = json.dumps([chunk for _score, chunk in ranked])
    assert "cohere-test-key" not in dumped


def test_hybrid_query_fuses_dense_and_sparse_then_reranks(monkeypatch):
    monkeypatch.setenv("BRASALAND_RAG_BACKEND", "qdrant")
    monkeypatch.setenv("BRASALAND_RAG_EMBEDDINGS", "local")
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.setenv("BRASALAND_RAG_RERANK", "local")
    pipelines = __import__("data.pipelines.rag", fromlist=["search_qdrant", "retrieve"])
    monkeypatch.setattr(pipelines, "_qdrant_models", lambda: _Models)
    captured = {}

    class _Client:
        def get_collection(self, collection_name):
            captured["collection"] = collection_name
            return _sparse_collection()

        def query_points(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                points=[
                    _payload_point(0.05, WASTE),
                    _payload_point(0.04, ALLERGEN),
                ]
            )

    monkeypatch.setattr(pipelines, "qdrant_client", lambda: _Client())
    hits = pipelines.search_qdrant([0.0] * 384, 8, "house sauce soy sulfites")
    prefetch = captured["kwargs"]["prefetch"]
    assert captured["kwargs"]["query"].fusion == "rrf"
    assert {item.using for item in prefetch} == {"dense", "bm25"}
    sparse = next(item for item in prefetch if item.using == "bm25")
    assert sparse.query.indices
    assert hits[0][0] == pytest.approx(1.0)
    assert hits[1][0] == pytest.approx(0.8)

    found = pipelines.retrieve("house sauce soy sulfites", k=2)
    assert found[0]["source_document"] == ALLERGEN["source_document"]
    assert found[1]["source_document"] == WASTE["source_document"]
    assert found[0]["score"] > found[1]["score"]


def test_legacy_dense_collection_skips_sparse_prefetch(monkeypatch):
    pipelines = __import__("data.pipelines.rag", fromlist=["search_qdrant"])
    captured = {}

    class _Client:
        def get_collection(self, collection_name):
            return _dense_collection()

        def query_points(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(points=[_payload_point(0.88, ALLERGEN)])

    monkeypatch.setattr(pipelines, "qdrant_client", lambda: _Client())
    hits = pipelines.search_qdrant([0.1, 0.2], 3, "house sauce")
    assert "prefetch" not in captured
    assert captured["query"] == [0.1, 0.2]
    assert hits[0][0] == pytest.approx(0.88)
    assert hits[0][1]["text"].startswith("House Sauce")


def test_bm25_lite_ranks_keyword_overlap():
    pipelines = __import__("data.pipelines.rag", fromlist=["bm25_lite"])
    question = "house sauce soy sulfites"
    matching = pipelines.bm25_lite(question, ALLERGEN["text"])
    other = pipelines.bm25_lite(question, WASTE["text"])
    assert matching > other
    assert 0.0 <= other <= matching <= 1.0
