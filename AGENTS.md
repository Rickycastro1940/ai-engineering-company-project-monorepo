# AGENTS.md

## Cursor Cloud specific instructions

This repo is the 4Geeks Academy AI Engineering monorepo template. At the current
commit the only runnable code is a single FastAPI process plus a CLI agent.
Setup and run commands are documented in `README.md` and
`services/api/README.md`; the notes below only cover non-obvious caveats.

### Services overview

- FastAPI API (`api/app.py`, a shim re-exporting `services/api/app.py`). Serves
  the inventory REST API (`/inventory`), the incident-analysis API
  (`/api/incidents/*`), and the static incident-analysis web UI mounted at `/`.
  This single process is all you need for the core product.
- Inventory CLI agent (`agent.py`). Optional/secondary. A plain-Python Groq
  tool-calling loop that talks to the running API. Requires the API to be up and
  a valid `GROQ_API_KEY`.
- Incident analysis CLI (`scripts/analyze.py`). Standalone, no server needed.

### Running (dev)

- The `uvicorn` console script installs to `~/.local/bin`, which is not on PATH.
  Run it as a module instead: `python3 -m uvicorn api.app:app --reload`.
- Use `python3` (there is no `python` symlink in this environment).
- The web UI's default "Input CSV path" field is `data/incidents.csv`, which does
  NOT exist in the repo. Use the shipped sample `scripts/incidents-COMPANY.csv`
  when exercising the analyzer via the UI or the `/api/incidents/*` endpoints.

### GROQ_API_KEY

- `agent.py` exits immediately (code 1) unless `GROQ_API_KEY` is set to a real
  key (placeholder `your_key_here` is rejected). The FastAPI service itself does
  NOT need any key — only the inventory agent does. Provide the key via repo
  Secrets (or a root `.env`, which is gitignored) to test the agent path.

### Tests / lint

- There is no automated test suite, no linter config, and no build step in this
  repo. "Build" is just running the Python app. Validate changes by running the
  API and exercising the endpoints / web UI, or by running `scripts/analyze.py`.

### Generated files (gitignored)

- `results.csv`, `scripts/results.csv`, `conversation_log.csv`,
  `data/uploads/*`. Inventory mutations write back to the committed
  `products.csv`; `git checkout products.csv` to reset seed data after testing.
