"""Endpoint evals for the LangGraph support agent (Part 1).

``POST /agent/query`` must only invoke the compiled graph — no retrieve/generate
business logic in the HTTP layer — and must never return a raw stack trace.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from services.agent.app import app


client = TestClient(app, raise_server_exceptions=False)


def test_agent_query_endpoint_invokes_graph_only():
    """Endpoint is a thin adapter: calls run_agent, returns answer + trace_id."""
    with patch("services.agent.router.run_agent") as mock_run:
        mock_run.return_value = {
            "status": "ok",
            "answer": "Locations must keep at least 3 days of main protein inventory.",
            "trace_id": "trace-endpoint-1",
            "error": None,
            "steps": [],
            "node_order": ["receive_question", "retrieve", "generate"],
        }
        response = client.post(
            "/agent/query",
            json={"question": "What is the minimum stock rule for proteins?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Locations must keep at least 3 days")
    assert body["trace_id"] == "trace-endpoint-1"
    assert body["status"] == "ok"
    assert body.get("error") is None
    mock_run.assert_called_once_with("What is the minimum stock rule for proteins?")


def test_agent_query_empty_question_returns_clear_400():
    response = client.post("/agent/query", json={"question": "   "})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "empty" in detail.lower()
    assert "traceback" not in response.text.lower()
    assert "Traceback" not in response.text


def test_agent_query_graph_failure_returns_clear_500_without_stack():
    with patch("services.agent.router.run_agent") as mock_run:
        mock_run.return_value = {
            "status": "error",
            "answer": None,
            "trace_id": "trace-error-1",
            "error": "The agent failed while processing the question.",
            "steps": [],
            "node_order": [],
        }
        response = client.post("/agent/query", json={"question": "trigger failure"})

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail == "The agent failed while processing the question."
    assert "traceback" not in response.text.lower()
    assert "RuntimeError" not in response.text
    assert "blowup" not in response.text


def test_agent_coexists_with_health_and_traces_routes():
    paths = set(client.get("/openapi.json").json()["paths"])
    assert "/agent/query" in paths
    assert "/agent/traces" in paths
    assert "/agent/traces/{trace_id}" in paths
    assert client.get("/health").json()["status"] == "ok"
