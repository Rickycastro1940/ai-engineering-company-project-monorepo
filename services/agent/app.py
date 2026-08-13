"""Standalone FastAPI app for the Brasaland LangGraph support agent + RFP intake.

Run (from repo root):

    uv run uvicorn services.agent.app:app --reload --port 8000

Endpoints:
  POST /agent/query
  GET  /agent/traces/{trace_id}
  GET  /agent/guardrails/summary
  POST /agent/guardrails/session
  POST /rfp/tickets
  GET  /rfp/tickets/{ticket_id}
  Backoffice UI: /rfp-upload.html (mounted from uis/backoffice)
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Compile the graph at import time so structural errors fail before serving.
from services.agent.graph import get_compiled_graph  # noqa: E402
from services.agent.router import router as agent_router  # noqa: E402
from services.rfp import router as rfp_router  # noqa: E402
from services.rfp.store import init_db  # noqa: E402

get_compiled_graph()
init_db()

app = FastAPI(
    title="Brasaland Support Agent + RFP Intake",
    version="1.0.0",
    description="LangGraph agent + Milestone 9 RFP intake (same process / same API).",
)
app.include_router(agent_router)
app.include_router(rfp_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "brasaland-support-agent"}


# Mount backoffice last so /rfp API routes win.
_BACKOFFICE = REPO_ROOT / "uis" / "backoffice"
if _BACKOFFICE.is_dir():
    app.mount("/", StaticFiles(directory=str(_BACKOFFICE), html=True), name="backoffice")
