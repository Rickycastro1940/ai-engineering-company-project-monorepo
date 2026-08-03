# AGENTS.md

## Cursor Cloud specific instructions

This repo is a Python monorepo (4Geeks AI Engineering template). The runnable parts are a
FastAPI backend, a static web UI it serves, a standalone incident-analysis CLI, and a Groq
chat agent. There are no automated tests and no linter configured.

### Environment
- Python 3.12. Dependencies are installed into a repo-local virtualenv at `.venv` by the
  startup update script (`pip install -r requirements.txt`). Activate it before running
  anything: `source .venv/bin/activate`.
- System package `python3.12-venv` is required to create the venv; it is already present on
  the snapshot.

### Services / how to run
- **FastAPI API + web UI (primary service).** From repo root: `uvicorn api.app:app --host 127.0.0.1 --port 8000`.
  - `api/app.py` is a thin shim that loads the real app from `services/api/app.py`. The app
    modules use bare imports (e.g. `from analyzer import ...`), which only resolve because
    the shim inserts `services/api` onto `sys.path`. Always launch via `api.app:app` (or
    `python services/api/main.py`), not by importing `services/api/app.py` directly.
  - Inventory endpoints (`/inventory`, `POST /inventory`, `PATCH /inventory/{id}`,
    `/inventory/alerts`) read/write `products.csv` at the repo root — a real file write, so
    POST/PATCH mutate the tracked seed file. Restore it with `git checkout -- products.csv`
    after testing if you don't want the change committed.
  - Incident analyzer endpoints live under `/api/incidents/...`. Note the intentionally
    misspelled `anylayze` route prefix exists alongside the correct `analyze` prefix (the
    web UI calls `anylayze`). Both work.
  - The web UI is served at `/` from `uis/web/index.html`. Its default "Input CSV path" is
    `data/incidents.csv`, which does NOT exist in the repo; use `scripts/incidents-COMPANY.csv`
    as a working sample input.
- **Incident analysis CLI.** `python scripts/analyze.py` (defaults to
  `scripts/incidents-COMPANY.csv`, writes `scripts/results.csv`).
- **Groq inventory agent.** `python agent.py`. Requires the API to already be running (it
  exits early if `http://127.0.0.1:8000` is unreachable) AND a valid `GROQ_API_KEY`
  (set in env or a root `.env`). Without a real key the agent starts, reaches the LLM call,
  and fails with a Groq 401 — everything except the LLM call is exercisable offline.

### Notes
- `conversation_log.csv`, `results.csv`, and `scripts/results.csv` are git-ignored runtime
  outputs.
- `packages/shared/package.json` is a stub (`@repo/shared-types`) with no build/runner; there
  is no Node workspace to install.
