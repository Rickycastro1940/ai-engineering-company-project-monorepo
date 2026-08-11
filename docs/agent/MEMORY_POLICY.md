# Agent memory policy (from `CONTEXT-company.md`)

Milestone kickoff — **Agent Memory and Self-Improvement (Part 1 of 2)**.

Source of truth: [`CONTEXT-company.md`](../../CONTEXT-company.md).
This file turns that company context into **what the Brasaland support agent
may remember** vs **what must never enter agent memory**.

## Must NEVER enter agent memory

Do not persist, summarize into long-term memory, or treat as recallable facts:

| Category | Why (company context) |
| -------- | --------------------- |
| Currency conversions (USD ↔ COP) | CONTEXT: keep USD $ and COP $ exactly as written — never convert |
| Absolute allergen safety claims (`zero risk`, `100% safe`, guaranteed no cross-contamination) | CONTEXT + allergen guide: never claim zero risk; follow source wording |
| Invented KB answers when sources are missing | CONTEXT: respond with *"There is not enough information available."* — do not “learn” a guess |
| Raw RAG internals (chunks, scores, Qdrant payloads) | CONTEXT: `POST /knowledge/query` returns answer string only |
| Secrets / tokens / OAuth credentials / API keys | Operational security; not company commercial knowledge |
| Customer payment data, passwords, government IDs | Not in the approved knowledge base; not needed for commercial/ops answers |
| Speculative people/roles/policies not in KB or tools | Only documented key people and procedures are authoritative |

If a turn contains any of the above, **discard it for memory writes** (still
answer the user safely in-session when appropriate).

## Facts worth remembering

Durable memory should prefer **reusable commercial / operations facts** that
match Brasaland’s knowledge domains and audience (salesperson / ops teams):

| Kind | Examples grounded in CONTEXT |
| ---- | ---------------------------- |
| Procurement / stock procedures | Minimum protein stock (3 days), emergency order approval **> 500 USD** by Lucía Fernández |
| Waste / escalation policy | Waste categories, daily logging, thresholds; escalate to Felipe Guerrero |
| Loyalty program rules | Brasa Points tiers and redemption rules (as written in KB) |
| Menu allergen disclosures | Declared allergens per dish; protocol steps; gluten-free limitations — **without** inventing safety guarantees |
| Authoritative people / roles | Mariana (CEO), Felipe Guerrero (Operations), Lucía Fernández (Procurement) |
| Stable ticket / inventory outcomes the agent already confirmed via tools/MCP | e.g. incident id + status from Incidents Manager — not invented statuses |

Prefer **semantic** facts (what is true for Brasaland) over dumping full chat
transcripts. Episodic traces belong in existing agent traces, not as unfiltered
memory blobs.

## Approved knowledge sources (memory should align with these)

Index / ground memory against the same KB files CONTEXT lists:

- `docs/company-knowledge-base/brasaland-supplier-ordering.en.md`
- `docs/company-knowledge-base/brasaland-waste-protocol.en.md`
- `docs/company-knowledge-base/brasaland-loyalty-program.en.md`
- `docs/company-knowledge-base/brasaland-menu-allergens.en.md`

Plus live tools already on the graph (MCP incidents, inventory reads) — never a
parallel invented store.

## Implementation notes for Part 1

- Branch base: MCP / LangGraph progress (`cursor/mcp-playground-connection-2e12`)
- **Same agent:** memory nodes extend `services/agent` — they do not replace
  MCP ticket lookup, inventory tools, or RAG retrieve/generate
- Keep memory writes behind an explicit allowlist derived from this policy
- Reject memory candidates that violate the “must never” table before persist
- Collection / company slug for RAG remain `brasaland_kb` / `brasaland`
- **Backend choice:** SQLite semantic store + existing agent traces (episodic).
  Rationale: [`MEMORY_BACKEND.md`](./MEMORY_BACKEND.md).
- **Access pattern:** explicit [`MemoryInterface`](./MEMORY_INTERFACE.md)
  `read` / `write` only — never accumulate by appending the store to the
  system prompt.
- Store path: `data/process/agent-memory/semantic.sqlite` (override with
  `AGENT_MEMORY_PATH`)
- **Dependencies:** Part 1 memory uses the existing stack only (stdlib
  `sqlite3` + LangGraph already in the project). Any *new* package must be
  added with ``uv add`` — never ``pip install`` / ``pipenv``.
