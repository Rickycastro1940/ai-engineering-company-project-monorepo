# API Service

This folder exposes the incident analyzer backend under the required monorepo path.

## Run

From repository root:

```bash
python services/api/main.py
```

The FastAPI app includes:

- `POST /api/incidents/anylayze`
- `POST /api/incidents/anylayze/upload`
- `POST /api/incidents/anylayze/summary`
- `POST /api/incidents/anylayze/upload/summary`
- `GET /api/incidents/results/export`

Aliases for `/analyze` endpoints are also available.
