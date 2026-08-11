# `services/agent` — Brasaland Support Agent (LangGraph + MCP)

LangGraph orchestration around the existing Brasaland RAG flow. Ticket status
goes through the **company-tools MCP server** (`langchain-mcp-adapters`);
inventory remains a read-only HTTP tool against the inventory manager.

## Milestone — Agent Memory (Part 1 of 2)

- [x] **Read `CONTEXT-company.md`** — memory allow/deny derived in
  [`docs/agent/MEMORY_POLICY.md`](../../docs/agent/MEMORY_POLICY.md).
- [x] **Branch from MCP / LangGraph progress** —
  `cursor/agent-memory-part1-2e12` (from `cursor/mcp-playground-connection-2e12`).
- [x] **Extend the same LangGraph agent** — `recall_memory` / `write_memory`
  nodes sit on the existing MCP + RAG graph; `lookup_ticket` still uses
  `lookup_ticket_via_mcp` only (does not replace MCP/tools/RAG).
- [x] Enforce “must never enter memory” filters on every write (`memory/policy.py`).
- [x] Persist only facts worth remembering (`data/process/agent-memory/semantic.sqlite`).
- [x] **Self-evaluation after each relevant interaction** — explicit
  new/corrected/skip criterion ([`docs/agent/MEMORY_SELF_EVAL.md`](../../docs/agent/MEMORY_SELF_EVAL.md));
  does **not** always write.
- [x] **Backend documented** — SQLite semantic + traces episodic
  ([`docs/agent/MEMORY_BACKEND.md`](../../docs/agent/MEMORY_BACKEND.md)).
- [x] **Explicit read/write interface** — `MemoryInterface.read` /
  `MemoryInterface.write` ([`docs/agent/MEMORY_INTERFACE.md`](../../docs/agent/MEMORY_INTERFACE.md));
  does **not** accumulate state by appending the store to the system prompt.

```text
… → decide_route → recall_memory → lookup_ticket (MCP) | lookup_inventory | retrieve
                                         ↓
                              answer_* / generate → write_memory → END
```

## MCP migration (company tools)

- [x] **Connect via `langchain-mcp-adapters`** — `tools/mcp_incidents.py` loads
  `manage_incident_ticket` from the company-tools MCP server (Streamable HTTP +
  OAuth) and the graph `lookup_ticket` node calls `lookup_ticket_via_mcp` only.
- [x] **Single path to Incidents Manager** — direct HTTP `lookup_ticket` is
  deprecated (`DeprecationWarning`), not re-exported from `tools/__init__.py`,
  and not wired into the compiled graph.
- [x] **RAG vs tools routing unchanged** — `decide_route` + conditional edges
  still choose RAG / ticket / inventory; only the ticket transport is MCP.

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
| `MCP_SERVER_URL` | Company-tools MCP endpoint (default `http://127.0.0.1:3001/mcp`) |
| `MCP_ACCESS_TOKEN` | Bearer access token for MCP Auth (optional; agent can mint from issuer) |
| `MCP_AUTH_ISSUER` | OIDC issuer for minting tokens (default `http://127.0.0.1:3002`) |
| `MCP_CLIENT_ID` | OAuth client id when minting (default `agent-support-prod`) |
| `COMPANY_API_BASE` / `INCIDENT_API_BASE` | Upstream used by the MCP server (not by the graph ticket node) |

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
