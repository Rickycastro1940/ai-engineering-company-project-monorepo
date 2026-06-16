# API Service

This folder exposes the incident analyzer backend and inventory API under the required monorepo path.

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

## Inventory endpoints

Inventory data is stored in [`products.csv`](../../products.csv) at the repository root.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/inventory` | List all products |
| `POST` | `/inventory` | Add a product (`name`, `quantity`, `unit`) |
| `PATCH` | `/inventory/{product_id}` | Update stock by `delta` (+ incoming, − outgoing) |
| `GET` | `/inventory/alerts` | Products below threshold (default `10`) |

### Examples

```bash
curl http://127.0.0.1:8000/inventory

curl -X POST http://127.0.0.1:8000/inventory \
  -H "Content-Type: application/json" \
  -d '{"name":"Olive Oil","quantity":15,"unit":"liters"}'

curl -X PATCH http://127.0.0.1:8000/inventory/1 \
  -H "Content-Type: application/json" \
  -d '{"delta":5}'

curl http://127.0.0.1:8000/inventory/alerts
curl "http://127.0.0.1:8000/inventory/alerts?threshold=20"
```

Interactive docs: `http://127.0.0.1:8000/docs`

## Incident analysis endpoints

The FastAPI app also includes:

- `POST /api/incidents/anylayze`
- `POST /api/incidents/anylayze/upload`
- `POST /api/incidents/anylayze/summary`
- `POST /api/incidents/anylayze/upload/summary`
- `GET /api/incidents/results/export`

Aliases for `/analyze` endpoints are also available.
