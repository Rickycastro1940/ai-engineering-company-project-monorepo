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

The agent runs an interactive CLI backed by Groq. It defines the inventory API endpoints as LLM tools, keeps conversation history in memory for the session, and appends every turn to `conversation_log.csv`.

Set `GROQ_API_KEY` in a root `.env` file before starting the agent.

## Conversation log

The agent appends every event to [`conversation_log.csv`](../../conversation_log.csv) at the repository root. The file is **append-only** and persists across sessions (new rows are never overwritten).

| Column | Description |
|--------|-------------|
| `actor` | Who produced the event: `user`, `agent`, `tool`, or `system` |
| `message` | User text, agent reply, or JSON tool result |
| `tool_call` | JSON tool request from the agent, or tool name on result rows |
| `timestamp` | UTC ISO-8601 timestamp |

Example flow for one user question:

```text
user   | List all products              |              | 2026-...
agent  |                                | {"name":"list_inventory","arguments":{}} | 2026-...
tool   | [{"product_id":1,...}]         | list_inventory | 2026-...
agent  | We have Tomatoes, Mozzarella... |              | 2026-...
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
