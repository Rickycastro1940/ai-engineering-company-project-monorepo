"""Existing Brasaland RAG pipeline tests (must still pass alongside agent evals)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from data.pipelines.rag import (
    DEFAULT_K,
    MIN_SCORE,
    NO_CONTEXT_ANSWER,
    generate_answer,
    query,
    retrieve,
)


@patch("data.pipelines.rag.qdrant_client")
@patch("data.pipelines.rag.embed")
def test_retrieve_filters_by_min_score(mock_embed, mock_qdrant):
    mock_embed.return_value = [0.1] * 1536
    hit_high = MagicMock(score=0.85, payload={"text": "High score chunk", "source_document": "supplier-ordering"})
    hit_low = MagicMock(score=0.50, payload={"text": "Low score chunk", "source_document": "waste-protocol"})
    mock_qdrant.search.return_value = [hit_high, hit_low]

    results = retrieve("sample query", k=5, min_score=0.70)

    assert len(results) == 1
    assert results[0]["text"] == "High score chunk"
    assert results[0]["_score"] == 0.85
    mock_embed.assert_called_once_with("sample query")


@patch("data.pipelines.rag.generate_answer", return_value="Locations must keep 3 days of protein stock.")
@patch("data.pipelines.rag.retrieve")
def test_query_orchestrates_retrieve_then_generate(mock_retrieve, mock_generate):
    mock_retrieve.return_value = [
        {"text": "Minimum stock rule: 3 days of main protein inventory.", "source_document": "supplier-ordering"}
    ]

    answer = query("What is the minimum stock rule for proteins?")

    mock_retrieve.assert_called_once()
    mock_generate.assert_called_once()
    assert "3 days" in answer


@patch("data.pipelines.rag.generate_answer")
@patch("data.pipelines.rag.retrieve", return_value=[])
def test_query_returns_fallback_when_no_chunks(mock_retrieve, mock_generate):
    answer = query("Unknown topic?")
    assert answer == NO_CONTEXT_ANSWER
    mock_generate.assert_not_called()


@patch("data.pipelines.rag.retrieve")
@patch("data.pipelines.rag.client")
def test_generate_answer_does_not_call_retrieve(mock_client, mock_retrieve):
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="Grounded answer"))
    ]
    answer = generate_answer(
        "What is the minimum stock rule?",
        [{"text": "3 days of main protein inventory.", "source_document": "supplier-ordering"}],
    )
    mock_retrieve.assert_not_called()
    assert answer == "Grounded answer"
