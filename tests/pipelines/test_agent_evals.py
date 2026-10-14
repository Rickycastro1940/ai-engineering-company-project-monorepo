"""Support-graph evals. Assertions read the stored trace, not a live chat model.

Department: Training (Jake Morrison) + Executive (Mariana Restrepo). The graph
reuses ``data.pipelines.rag.retrieve`` and ``generate_answer``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.agent.graph import agent_graph, run_agent  # noqa: E402
from services.agent.nodes import receive_question  # noqa: E402
from services.agent.state import AgentState  # noqa: E402
from services.agent.tracing import clear_traces, get_trace  # noqa: E402

HOUSE_SAUCE = "What allergens are in the House Sauce?"


@pytest.fixture(autouse=True)
def _offline_rag(monkeypatch):
    monkeypatch.setenv("BRASALAND_RAG_BACKEND", "local")
    monkeypatch.setenv("BRASALAND_RAG_EMBEDDINGS", "local")
    monkeypatch.setenv("BRASALAND_RAG_LLM", "extractive")
    clear_traces()


def test_trace_runs_retrieve_before_query():
    result = run_agent(HOUSE_SAUCE)
    trace = get_trace(result["trace_id"])
    assert trace is not None
    nodes = trace["nodes"]
    assert nodes.index("retrieve") < nodes.index("query")
    assert "receive_question" in nodes
    assert trace["checkpoint_id"]


def test_house_sauce_answer_stays_grounded_in_the_knowledge_base():
    result = run_agent(HOUSE_SAUCE)
    trace = get_trace(result["trace_id"])
    assert trace is not None
    answer = (trace["answer"] or "").lower()
    assert "soy" in answer
    assert "sulfites" in answer
    assert "brasaland-menu-allergens.en.md" in (trace["answer"] or "")
    snapshot = agent_graph.get_state({"configurable": {"thread_id": result["trace_id"]}})
    assert "soy" in (snapshot.values.get("answer") or "").lower()


def test_empty_question_stops_before_retrieve_and_query():
    result = run_agent("   ")
    trace = get_trace(result["trace_id"])
    assert trace is not None
    assert trace["nodes"] == ["receive_question"]
    assert "retrieve" not in trace["nodes"]
    assert "query" not in trace["nodes"]
    assert trace["error"] == "Question cannot be empty."
    assert trace["answer"] is None


def test_unknown_question_takes_the_honest_branch():
    result = run_agent("What is the capital of Japan?")
    trace = get_trace(result["trace_id"])
    assert trace is not None
    assert trace["nodes"] == ["receive_question", "retrieve", "honest_answer"]
    assert "query" not in trace["nodes"]
    assert "not enough information" in (trace["answer"] or "").lower()


def test_nodes_call_retrieve_and_generate_answer_not_query(monkeypatch):
    calls = {"retrieve": 0, "generate": 0, "query": 0}

    def fake_retrieve(query_str, k=5, min_score=None):
        calls["retrieve"] += 1
        return [
            {
                "source_document": "brasaland-menu-allergens.en.md",
                "section": "Menu Allergen Guide",
                "text": "House Sauce contains soy and sulfites.",
                "score": 0.9,
                "chunk_index": 0,
                "language": "en",
            }
        ]

    def fake_generate(question, context):
        calls["generate"] += 1
        assert context and context[0]["text"].startswith("House Sauce")
        return "House Sauce contains soy and sulfites."

    def fake_query(question):
        calls["query"] += 1
        return "should not run"

    monkeypatch.setattr("services.agent.nodes.retrieve", fake_retrieve)
    monkeypatch.setattr("services.agent.nodes.generate_answer", fake_generate)
    monkeypatch.setattr("data.pipelines.rag.query", fake_query)

    result = run_agent(HOUSE_SAUCE)
    trace = get_trace(result["trace_id"])
    assert calls == {"retrieve": 1, "generate": 1, "query": 0}
    assert trace["nodes"].index("retrieve") < trace["nodes"].index("query")
    assert "soy" in trace["answer"]


def test_compile_fails_when_an_edge_names_an_unknown_node():
    builder = StateGraph(AgentState)
    builder.add_node("receive_question", receive_question)
    builder.set_entry_point("receive_question")
    builder.add_edge("receive_question", "missing_node")
    with pytest.raises(ValueError, match="unknown node"):
        builder.compile(checkpointer=MemorySaver())


@pytest.fixture(scope="module")
def client():
    from api.app import app

    return TestClient(app)


def test_agent_endpoint_returns_answer_and_queryable_trace(client):
    response = client.post("/agent/query", json={"question": HOUSE_SAUCE})
    assert response.status_code == 200
    body = response.json()
    assert "soy" in body["answer"].lower()
    assert "sulfites" in body["answer"].lower()
    trace = client.get(f"/agent/traces/{body['trace_id']}")
    assert trace.status_code == 200
    steps = trace.json()["nodes"]
    assert steps.index("retrieve") < steps.index("query")


def test_agent_endpoint_rejects_an_empty_question_without_a_traceback(client):
    response = client.post("/agent/query", json={"question": "   "})
    assert response.status_code == 400
    text = response.text.lower()
    assert "empty" in text
    assert "traceback" not in text
    assert 'file "' not in text
