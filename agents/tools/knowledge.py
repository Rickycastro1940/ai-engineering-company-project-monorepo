"""Read the Brasaland knowledge base the same way `POST /knowledge/query` does."""

from __future__ import annotations

from data.pipelines.rag import answer_question


def query_standards(question: str, k: int = 3) -> dict:
    """Return a grounded answer and the cited chunks. No network in the default path."""
    return answer_question(question, k=k)
