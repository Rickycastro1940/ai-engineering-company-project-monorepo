# API Service

This folder exposes the incident analyzer backend and inventory API under the required monorepo path.

## Launch guide

### Prerequisites

1. Install dependencies from the repository root:

```bash
pip install -r requirements.txt
```

2. Create a `.env` file at the repository root with your Groq API key:

```env
GROQ_API_KEY=your_key_here
```

Do not commit `.env` — it is listed in `.gitignore`.

### Start order (required)

**The API must be running before the agent starts.** Use two terminals from the repository root:

```bash
# Terminal 1 — start the API first
uvicorn api.app:app --reload
```

Wait until you see `Application startup complete`, then:

```bash
# Terminal 2 — start the agent
python agent.py
```

If Terminal 2 starts before the API is ready, `agent.py` prints an error and exits:

```text
Could not reach the API. Start it first with: uvicorn api.app:app --reload
```

### Agent design note

The inventory agent in [`agent.py`](../../agent.py) is implemented **manually in plain Python**:

- No LangChain, LlamaIndex, AutoGen, or similar frameworks
- Tool definitions, the observe/think/act/update loop, API calls, and CLI are all written directly in `agent.py`
- The only external LLM dependency is the OpenAI-compatible Groq client (`openai` package)

## Local development summary

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

## Authentication / password reset

Password-reset endpoints and pages. Users are stored in `users.csv` at the repo root
(passwords hashed with PBKDF2-SHA256); reset tokens are stored in `password_resets.csv`
(git-ignored, runtime only). Reset emails are sent through [Resend](https://resend.com).

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/forgot-password` | Body `{email}`. Always returns `200` with a generic message (no account enumeration). If the email is registered, issues a token and emails a reset link. |
| `POST` | `/auth/reset-password` | Body `{token, password}`. Sets the new password and invalidates the token on success. Returns `400` for invalid/expired/used tokens. |
| `POST` | `/auth/login` | Body `{email, password}`. Returns `200` on valid credentials, `401` otherwise. |

### Pages (served as static HTML)

- `/forgot-password` — request a reset link; shows a confirmation regardless of result.
- `/reset-password?token=...` — set a new password; redirects to `/login` on success, shows an error with a link back to `/forgot-password` on failure.
- `/login` — includes a "Forgot your password?" link.

### Configuration (all from environment variables — never hardcoded)

| Variable | Default | Purpose |
|----------|---------|---------|
| `RESEND_API_KEY` | (none) | Resend API key. If unset, the email send is skipped (the endpoint still returns `200`). |
| `RESET_EMAIL_FROM` | `onboarding@resend.dev` | Sender address. The Resend test sender only delivers to the account owner; verify a domain to send elsewhere. |
| `APP_BASE_URL` | `http://127.0.0.1:8000` | Base URL used to build the reset link. |
| `RESET_TOKEN_TTL_MINUTES` | `30` | Reset-token lifetime in minutes. |

## Incident analysis endpoints

The FastAPI app also includes:

- `POST /api/incidents/anylayze`
- `POST /api/incidents/anylayze/upload`
- `POST /api/incidents/anylayze/summary`
- `POST /api/incidents/anylayze/upload/summary`
- `GET /api/incidents/results/export`

Aliases for `/analyze` endpoints are also available.

## Evaluation checklist

How to verify each rubric item:

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Four FastAPI inventory endpoints | `curl` examples above + `http://127.0.0.1:8000/docs` |
| 2 | `products.csv` survives restart | `POST` a product, restart `uvicorn`, `GET /inventory` — product still present |
| 3 | Agent loop (Observe → Think → Act → Update → Repeat) | See `run_agent_turn()` in [`agent.py`](../../agent.py) |
| 4 | Tools with name, description, typed params | `TOOLS` constant in [`agent.py`](../../agent.py) |
| 5 | Agent calls correct API on tool selection | `execute_tool()` maps each tool to `/inventory` routes |
| 6 | Tool result injected before next LLM call | `messages.append({"role": "tool", ...})` in `run_agent_turn()` |
| 7 | `conversation_log.csv` with 4 fields per event | Run agent; check `actor,message,tool_call,timestamp` columns |
| 8 | Log append-only across sessions | Run `python agent.py` twice; rows accumulate, never overwritten |
| 9 | Multi-step interaction | Ask: *"Add 3 units of Olive Oil in liters, then tell me which products are low on stock."* — log shows `add_product` then `get_low_stock_alerts` |
| 10 | No agent framework | Plain Python loop only; no LangChain/LlamaIndex/AutoGen in `requirements.txt` |
