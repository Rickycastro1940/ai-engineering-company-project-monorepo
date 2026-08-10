"""Company FastAPI entry that mounts the knowledge RAG endpoint.

Prefer ``api.app:app`` (shim) or ``services.agent.app:app`` for the agent.
This module keeps a minimal knowledge-only surface for local smoke tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.api.routers.knowledge import router as knowledge_router  # noqa: E402

app = FastAPI(title="Brasaland Knowledge API", version="1.0.0")
app.include_router(knowledge_router)
