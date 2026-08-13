"""Standalone FastAPI app for the Brasaland LangGraph support agent.

Run (from repo root):

    uv run uvicorn services.agent.app:app --reload --port 8000

Endpoints:
  POST /agent/query
  GET  /agent/traces/{trace_id}
  GET  /agent/guardrails/summary
  POST /agent/guardrails/session
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Compile the graph at import time so structural errors fail before serving.
from services.agent.graph import get_compiled_graph  # noqa: E402
from services.agent.router import router as agent_router  # noqa: E402

get_compiled_graph()

app = FastAPI(
    title="Brasaland Support Agent",
    version="1.0.0",
    description="LangGraph Part 1 — explicit RAG agent flow with queryable traces.",
)
app.include_router(agent_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "brasaland-support-agent"}
