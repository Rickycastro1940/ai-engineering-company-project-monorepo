# API Service

This folder exposes the incident analyzer backend under the required monorepo path.

## Local development

From repository root, use two terminals:

```bash
# Terminal 1 — start the API
uvicorn api.app:app --reload

# Terminal 2 — start the agent
python agent.py
```

The root-level `api/` package is a compatibility shim that re-exports this service's FastAPI app so `uvicorn api.app:app` works from the repo root.

## Alternative run command

```bash
python services/api/main.py
```

## Endpoints

The FastAPI app includes:

- `POST /api/incidents/anylayze`
- `POST /api/incidents/anylayze/upload`
- `POST /api/incidents/anylayze/summary`
- `POST /api/incidents/anylayze/upload/summary`
- `GET /api/incidents/results/export`

Aliases for `/analyze` endpoints are also available.
