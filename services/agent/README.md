# `services/agent` — Brasaland Support Agent (LangGraph + MCP)

LangGraph orchestration around the existing Brasaland RAG flow. Ticket status
goes through the **company-tools MCP server** (`langchain-mcp-adapters`);
inventory remains a read-only HTTP tool against the inventory manager.

## MCP migration (company tools)

- [x] **MCP client** (`tools/mcp_incidents.py`) — `lookup_ticket` node calls
  `manage_incident_ticket` on `mcps/company_tools` via Streamable HTTP + OAuth.
- [x] **Direct HTTP deprecated** — `tools/ticket_lookup.py` is no longer wired
  into the graph (formatting helpers only).
- [x] **Routing unchanged** — RAG vs tools decision is the same; only the
  ticket transport changed.

## Part 2 checklist — Tools outside the RAG

- [x] **Typed contract** (`tools/contracts.py`) — `TicketLookupInput` /
  `TicketLookupOutput` / `TicketRecord` (same fields as
  `GET /api/incidents` / `GET /api/incidents/{id}`).
- [x] **Ticket tool (legacy HTTP)** (`tools/ticket_lookup.py`) — deprecated for
  graph use; kept for helpers / reference.
- [x] **Auth** — MCP path uses OAuth via MCP Auth; optional
  `INCIDENT_API_TOKEN` still forwarded by the MCP server to upstream GETs.
- [x] **Fallback** — `ticket_fallback` node when the tool times out, errors, or
  the ticket does not exist. Answer always includes
  *"I couldn't confirm that ticket's status right now"* — never a made-up
  status (`ABIERTO` / `CERRADO` / …).
- [x] **Stretch inventory tool** — typed `InventoryLookupInput` /
  `InventoryLookupOutput`; `GET /inventory/products` against CSV-backed
  inventory manager; same **5s** timeout + `inventory_fallback`; separate
  node from tickets (single responsibility).
- [x] **Routing** — explicit `decide_route` node + conditional edges choose RAG,
  ticket tool, inventory tool, or combinations from the question text.
- [x] **Ticket tool node** — `lookup_ticket` on the compiled graph (via MCP).
- [x] **Inventory tool node** — `lookup_inventory` on the compiled graph.
- [x] **Traces** — each run records `sources_used` (`ticket` / `inventory` /
  `rag`) and `node_order` so reviewers can see which source(s) ran and in
  what order; queryable via `GET /agent/traces?node=lookup_ticket`.
- [x] **Evals** — ≥2 routing evals (tool-required vs RAG-required) plus
  optional fallback (`tests/pipelines/test_agent_routing_evals.py`). Tool
  evals call the **real** incident/inventory FastAPI routes (company CSV),
  not simulated payloads.

## Agent routing (Part 2)

- [x] **Auto-decide** — `decide_route` inspects the question and chooses RAG,
  a tool, or both. The user never names the source.
- [x] **One job per tool** — `lookup_ticket` only hits incidents (via MCP);
  `lookup_inventory` only hits inventory. Never a combined “look up tickets
  or inventory” tool.

## Graph (Part 2)

```text
START → receive_question
            │
            ├── empty ──────────────► empty_question → END
            └── decide_route  (auto: ticket | inventory | rag | combinations)
                      │
                      ├── ticket / both / … ──► lookup_ticket  ← MCP → incidents
                      │                              │
                      │                              ├── (+ inventory) → lookup_inventory
                      │                              ├── answer_ticket / ticket_fallback
                      │                              └── retrieve (when also needs RAG)
                      ├── inventory / … ──────► lookup_inventory  ← products only
                      │                              │
                      │                              ├── answer_inventory / inventory_fallback
                      │                              └── retrieve (when also needs RAG)
                      └── retrieve (RAG only) ─► generate | no_context | …
```

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
