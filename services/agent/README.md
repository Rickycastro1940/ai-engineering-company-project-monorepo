# `services/agent` — Brasaland Support Agent (LangGraph Parts 1–2)

LangGraph orchestration around the existing Brasaland RAG flow, plus a
**read-only ticket tool** that queries the live incident manager.

## Part 2 checklist — Tools outside the RAG

- [x] **Typed contract** (`tools/contracts.py`) — `TicketLookupInput` /
  `TicketLookupOutput` / `TicketRecord` (same fields as
  `GET /api/incidents` / `GET /api/incidents/{id}`).
- [x] **Ticket tool** (`tools/ticket_lookup.py`) — HTTP GET to the incident
  manager (real CSV-backed store). Read-only. Explicit **5s** timeout.
- [x] **Auth** — incident GETs currently require **no auth**. Optional
  `INCIDENT_API_TOKEN` / `INCIDENT_API_KEY` env vars are forwarded as Bearer
  if set. Never hardcode tokens.
- [x] **Fallback** — timeout / not-found / service error → honest message,
  never an invented status (`ticket_fallback` node).
- [x] **Routing** — explicit `decide_route` node + conditional edges choose RAG,
  ticket tool, or both from the question text (no user hint required).
- [x] **Ticket tool node** — `lookup_ticket` on the compiled graph (HTTP GET only).
- [x] **Traces** — `sources_used` + `node_order` show which source(s) ran
  and in what order (including `decide_route` → `lookup_ticket` / `retrieve`).
- [x] **Evals** — `tests/pipelines/test_agent_tools.py` (tool-required,
  RAG-required, fallback).

## Graph (Part 2)

```text
START → receive_question
            │
            ├── empty ──────────────► empty_question → END
            └── decide_route  (conditional agent: ticket | rag | both)
                      │
                      ├── ticket / both ──────► lookup_ticket  ← tool node
                      │                              │
                      │                              ├── ticket_answer → answer_ticket → END
                      │                              ├── ticket_fallback → END
                      │                              └── retrieve (when needs_rag / both)
                      └── retrieve (RAG only) ─► generate | no_context | ticket_* → END
```

`decide_route` inspects the question and chooses the ticket tool **instead of**
or **in addition to** the RAG — the user never names the source.

## Ticket tool contract

**Input** (`TicketLookupInput`): `ticket_id` **or** search filters
(`status`, `category`, `location_id`, `date_from`, `date_to`).

**Output** (`TicketRecord` items): `incident_id`, `date`, `location_id`,
`category`, `description`, `status`, `customer_id`, `satisfaction_score`,
`reporter_id`, `source` — the same fields the incident API exposes.

## Environment

| Variable | Purpose |
|----------|---------|
| `INCIDENT_API_BASE` | Base URL for incident GETs (default `http://127.0.0.1:8000`) |
| `INCIDENT_API_TOKEN` / `INCIDENT_API_KEY` | Optional Bearer token (unused while the API has no auth) |

## API

```bash
# Start the company API (incidents + agent) from services/api so local imports resolve
cd services/api && PYTHONPATH=/workspace:/workspace/services/api \
  uv run uvicorn app:app --reload --host 127.0.0.1 --port 8000

# Or from repo root via the api/ shim:
# uv run uvicorn api.app:app --reload --port 8000

# Live incident endpoints used by the tool
curl -s http://127.0.0.1:8000/api/incidents/BRS-000002
curl -s 'http://127.0.0.1:8000/api/incidents?status=ABIERTO'

# Agent query (auto-routes)
curl -s -X POST http://127.0.0.1:8000/agent/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the status of ticket BRS-000002?"}'
```

## Evals

```bash
uv run pytest tests/pipelines/ -q
# Part 2 only:
uv run pytest tests/pipelines/test_agent_tools.py -q
```

## Part 1 (still required)

See checklist history below — state, retrieve/generate nodes, checkpointing,
grounding, and `POST /agent/query` remain in place.

- State (`state.py`) — minimal; no full conversation history
- RAG nodes reuse `data.pipelines.rag.retrieve` / `generate_answer`
- Compile-before-execute + `MemorySaver` checkpoints
- Queryable JSON traces under `data/process/agent-traces/`
