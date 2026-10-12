"""Brasaland FastAPI service entry (TinyDB auth + SQLModel inventory).

Canonical process: ``uvicorn api.app:app`` from the repo root.
This module re-exports that app so ``python services/main.py`` also works.
"""

from __future__ import annotations

import uvicorn

from api.app import app

__all__ = ["app"]


if __name__ == "__main__":
    uvicorn.run("api.app:app", host="127.0.0.1", port=8000, reload=True)
