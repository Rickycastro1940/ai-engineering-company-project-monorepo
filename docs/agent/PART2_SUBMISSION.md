# Part 2 submission — Tools Outside the RAG

**Branch:** `cursor/langgraph-agent-tools-b1ec`  
**PR:** https://github.com/Rickycastro1940/ai-engineering-company-project-monorepo/pull/19  
**Label:** `part-2-external-tools`

## Auth note

`GET /api/incidents` and `GET /api/incidents/{id}` currently require **no authentication**.
Optional `INCIDENT_API_TOKEN` / `INCIDENT_API_KEY` are forwarded as Bearer if set.
Inventory GETs (`GET /inventory/products`) likewise require **no auth** today.

## Tracing and evaluation (extended from Part 1)

- [x] **Each run's trace shows RAG / tool / both and order** via:
  - `sources_order` — e.g. `["ticket"]`, `["rag"]`, `["ticket", "rag"]`
  - `source_summary` — e.g. `ticket_only`, `rag_only`, `ticket_then_rag`
  - `node_order` / `steps[].sequence` — full node sequence
- [x] **Eval — tool required (not RAG):** `test_eval_tool_required_reads_real_incident_service_not_rag`
  in `tests/pipelines/test_agent_routing_evals.py` — calls real
  `GET /api/incidents/{id}` (company CSV), not a mocked ticket payload
- [x] **Eval — RAG required (not a tool):** `test_eval_rag_required_skips_tools`
- [x] **Optional fallback eval:** `test_eval_fallback_when_incident_service_unavailable`
- [x] **No simulated tool data** — ticket/inventory tools only HTTP GET the
  company backends (`incidents-COMPANY.csv`, `products.csv`)

Query after a run: `GET /agent/traces?source=ticket` or `?source=rag`.

## Artifacts

| Artifact | Path |
|----------|------|
| Tool-run trace (`ticket_only`) | [`docs/agent/part2-tool-run-trace.json`](part2-tool-run-trace.json) |
| RAG-run trace (`rag_only`) | [`docs/agent/part2-rag-run-trace.json`](part2-rag-run-trace.json) |
| Both-run trace (`ticket_then_rag`) | [`docs/agent/part2-both-run-trace.json`](part2-both-run-trace.json) |
| Live tool-run | [`docs/agent/part2-live-tool-run-trace.json`](part2-live-tool-run-trace.json) |
| Fallback-run trace | [`docs/agent/part2-fallback-run-trace.json`](part2-fallback-run-trace.json) |
| Eval output | [`docs/agent/part2-eval-output.txt`](part2-eval-output.txt) |

### Tool-run (ticket — not RAG)

- Question: status of ticket `BRS-000002`
- `sources_order`: `["ticket"]` · `source_summary`: `ticket_only`
- `node_order`: `receive_question` → `decide_route` → `lookup_ticket` → `answer_ticket`

### RAG-run (knowledge base — not a tool)

- Question: minimum stock rule for proteins
- `sources_order`: `["rag"]` · `source_summary`: `rag_only`
- `node_order`: `receive_question` → `decide_route` → `retrieve` → `generate`

### Both-run (tool then RAG)

- `sources_order`: `["ticket", "rag"]` · `source_summary`: `ticket_then_rag`

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
