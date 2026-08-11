# Persistent memory backend choice (Brasaland support agent)

## Decision

**Combination backend:**

| Layer | Backend | What it stores |
| ----- | ------- | -------------- |
| **Semantic memory** (“what is true”) | **SQLite** key/document store at `data/process/agent-memory/semantic.sqlite` | Policy-approved ops/commercial facts with `kind`, `source`, `metadata` |
| **Episodic memory** (“what happened”) | **Existing agent traces** (`data/process/agent-traces/*.json`) | Per-run node order, tool/MCP outcomes, answers — already queryable |

LangGraph’s in-process `MemorySaver` remains **working/short-term** checkpointing only (thread resume), not durable company memory.

## Why this fits what Brasaland needs to remember

From [`CONTEXT-company.md`](../../CONTEXT-company.md) and
[`MEMORY_POLICY.md`](./MEMORY_POLICY.md), the agent should remember **small,
reusable semantic facts** for commercial/ops teams — not full chat dumps and
not RAG internals:

- Procurement rules (e.g. 3-day protein stock, **> 500 USD** emergency approval
  by Lucía Fernández — currencies kept as written)
- Waste escalation (Felipe Guerrero)
- Loyalty / allergen disclosures **as written** (never “zero risk”)
- Key people/roles
- Confirmed MCP ticket / inventory outcomes (`BRS-…`, product quantities)

Those records are:

1. **Structured** — each fact has a `kind` (`procurement`, `allergen`, …) so
   policy can allow/deny before write.
2. **Deduplicated** — the same stock rule should upsert, not multiply.
3. **Exact** — ticket `BRS-000002 status=CERRADO` is an identity lookup, not a
   “similar chunk” problem.
4. **Low volume** — company ops facts and confirmed tool results, not millions
   of embeddings.

**SQLite** matches that profile: durable file on disk, SQL filters by `kind` /
text, ACID upserts, **stdlib only** (no new `uv add` service dependency), easy
to inspect and delete forbidden content.

**Existing traces** already capture episodic “what the agent did” (including
MCP `lookup_ticket`). Reusing them avoids a second transcript store and keeps
memory writes focused on semantic distillation.

## Why not the other options (alone)

| Option | Why it is not the primary Brasaland memory store |
| ------ | ------------------------------------------------ |
| **Redis alone** | Excellent cache/session KV, but needs a running Redis + `uv add redis`. Our durable needs are durable *facts*, not hot session state. Redis alone also lacks rich querying by `kind` without extra conventions. |
| **Qdrant / vector DB alone** | Already used for **RAG** collection `brasaland_kb`. Agent memory must **not** mix into that collection: CONTEXT forbids storing raw chunks/scores/payloads, and approximate nearest-neighbor is the wrong primary API for “remember confirmed ticket status” or “Lucía approves > 500 USD”. A separate memory collection would still fight structured policy filters and exact IDs. |
| **JSON file alone** | Fine for prototypes; SQLite keeps the same “local KV/document” idea with safer concurrent upserts and indexed lookups as the store grows. |
| **One store for everything** | Would blur RAG knowledge, episodic traces, and semantic memory — harder to enforce “must never enter memory” and easier to re-learn invented answers. |

## What we deliberately keep out of the backend

Per policy, the SQLite semantic store **rejects** before persist:

- Currency conversions, absolute allergen safety claims, unknown-answer
  placeholders, secrets/tokens, payment/PII, speculative roles, RAG internals

Failed tool paths and `no_context` answers do **not** write semantic memory
(graph routes them away from `write_memory`).

## How it extends the MCP agent (does not replace it)

```text
decide_route → recall_memory (MemoryInterface.read → SQLite)
            → lookup_ticket via MCP | inventory | RAG
            → answer/generate → write_memory (MemoryInterface.write)
```

Incidents Manager access remains **MCP-only**. SQLite only stores *approved
summaries* of confirmed outcomes and ops facts — never a parallel incidents API.

Explicit R/W API (no system-prompt accumulation):
[`MEMORY_INTERFACE.md`](./MEMORY_INTERFACE.md).

## Configuration

| Env | Default | Meaning |
| --- | ------- | ------- |
| `AGENT_MEMORY_PATH` | `data/process/agent-memory/semantic.sqlite` | SQLite file path |

## Dependencies

SQLite via Python’s **stdlib** `sqlite3` — no new package. If we later add Redis
or a dedicated memory vector collection, install with **`uv add`** only.

## Future extension (optional Part 2+)

If recall quality needs similarity over large fact sets, add a **secondary**
Qdrant collection (e.g. `brasaland_agent_memory`) *in addition to* SQLite —
never by writing into `brasaland_kb`. Redis could front hot reads. Primary
source of truth for policy-gated facts stays the structured store.
