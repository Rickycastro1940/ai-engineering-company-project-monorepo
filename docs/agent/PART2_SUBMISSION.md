# Part 2 submission — Tools Outside the RAG

**Branch:** `cursor/langgraph-agent-tools-b1ec`  
**PR:** https://github.com/Rickycastro1940/ai-engineering-company-project-monorepo/pull/19  
**Label:** `part-2-external-tools`  
**Base:** `main` (separate from Part 1)

## Required layout

```text
services/agent/          ← nodes + tools on the Part 1 graph
tests/pipelines/         ← routing and fallback evals
```

## Required PR artifacts

| Artifact | Path | What it shows |
|----------|------|----------------|
| **Ticket-tool run** | [`part2-tool-run-trace.json`](part2-tool-run-trace.json) | `source_summary: ticket_only` |
| **Live ticket-tool run** | [`part2-live-tool-run-trace.json`](part2-live-tool-run-trace.json) | Real `GET /api/incidents/BRS-000002` |
| **RAG run** | [`part2-rag-run-trace.json`](part2-rag-run-trace.json) | `source_summary: rag_only` |
| **Eval output** | [`part2-eval-output.txt`](part2-eval-output.txt) | New routing/fallback evals |

Also included: [`part2-both-run-trace.json`](part2-both-run-trace.json), [`part2-fallback-run-trace.json`](part2-fallback-run-trace.json).

### Ticket-tool trace (required)

- Question: *What is the status of ticket BRS-000002?*
- `sources_order`: `["ticket"]` · `source_summary`: `ticket_only`
- `node_order`: `receive_question` → `decide_route` → `lookup_ticket` → `answer_ticket`
- No RAG nodes (`retrieve` / `generate` absent)

### RAG trace (required — correct routing)

- Question: *What is the minimum stock rule for proteins?*
- `sources_order`: `["rag"]` · `source_summary`: `rag_only`
- `node_order`: `receive_question` → `decide_route` → `retrieve` → `generate`
- No tool nodes (`lookup_ticket` / `lookup_inventory` absent)

### Eval output (required)

```bash
uv run pytest tests/pipelines/test_agent_routing_evals.py \
  tests/pipelines/test_agent_tools.py \
  tests/pipelines/test_inventory_tool.py \
  tests/pipelines/test_ticket_tool_live.py -v
```

See [`part2-eval-output.txt`](part2-eval-output.txt) — **40 passed**.

Key evals in `tests/pipelines/test_agent_routing_evals.py`:

1. Tool-required (real `GET /api/incidents/{id}`, not RAG)
2. RAG-required (tools never called)
3. Optional fallback when incident service unavailable
4. Stretch inventory via real `GET /inventory/products`

## Auth

Incident and inventory **GET** routes require **no authentication** today.  
Optional: `INCIDENT_API_TOKEN` / `INVENTORY_API_TOKEN` as Bearer if set.

## Implementation map

| Area | Location |
|------|----------|
| Ticket tool | `services/agent/tools/ticket_lookup.py` |
| Inventory tool (stretch) | `services/agent/tools/inventory_lookup.py` |
| Typed contracts | `services/agent/tools/contracts.py` |
| Auto routing | `services/agent/tools/routing.py` + `decide_route` node |
| Graph | `services/agent/graph.py` |
| Traces | `sources_order` / `source_summary` / `node_order` |
