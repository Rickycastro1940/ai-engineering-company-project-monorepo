# Part 2 submission — Tools Outside the RAG

**Branch:** `cursor/langgraph-agent-tools-b1ec`  
**PR:** https://github.com/Rickycastro1940/ai-engineering-company-project-monorepo/pull/19  
**Label:** `part-2-external-tools`

## Auth note

`GET /api/incidents` and `GET /api/incidents/{id}` currently require **no authentication**.
Optional `INCIDENT_API_TOKEN` / `INCIDENT_API_KEY` are forwarded as Bearer if set.
Inventory GETs (`GET /inventory/products`) likewise require **no auth** today.

## Tracing and evaluation (extended from Part 1)

- [x] **Each run's trace shows RAG / tool / both and order** via `sources_used` + `node_order` (+ per-step `output.source`).
- [x] **Eval — tool required (not RAG):** `test_eval_tool_required_question_uses_ticket_not_rag`
- [x] **Eval — RAG required (not a tool):** `test_eval_rag_required_question_skips_ticket_tool`
- [x] **Optional fallback eval:** `test_eval_ticket_fallback_when_service_unavailable`

Query after a run: `GET /agent/traces?node=lookup_ticket` or `query_traces(node="retrieve")`.

## Artifacts

| Artifact | Path |
|----------|------|
| Tool-run trace | [`docs/agent/part2-tool-run-trace.json`](part2-tool-run-trace.json) |
| Live tool-run | [`docs/agent/part2-live-tool-run-trace.json`](part2-live-tool-run-trace.json) |
| RAG-run trace | [`docs/agent/part2-rag-run-trace.json`](part2-rag-run-trace.json) |
| Fallback-run trace | [`docs/agent/part2-fallback-run-trace.json`](part2-fallback-run-trace.json) |
| Eval output | [`docs/agent/part2-eval-output.txt`](part2-eval-output.txt) |

### Tool-run (ticket — not RAG)

- Question: status of ticket `BRS-000002`
- `node_order`: `receive_question` → `decide_route` → `lookup_ticket` → `answer_ticket`
- `sources_used`: `["ticket"]`
- No `retrieve` / `generate`

### RAG-run (knowledge base — not a tool)

- Question: minimum stock rule for proteins
- `node_order`: `receive_question` → `decide_route` → `retrieve` → `generate`
- `sources_used`: `["rag"]`
- No `lookup_ticket` / `lookup_inventory`

### Fallback-run (incident service unavailable)

- `node_order`: `receive_question` → `decide_route` → `lookup_ticket` → `ticket_fallback`
- Answer includes *"I couldn't confirm that ticket's status right now"* (no invented status)

### Evals

```text
28 passed  (test_agent_tools.py + test_inventory_tool.py)
```

## Typed contracts

- **Ticket:** `TicketLookupInput` / `TicketRecord` — same fields as `GET /api/incidents`
- **Inventory (stretch):** `InventoryLookupInput` / `InventoryProductRecord` — `GET /inventory/products`
