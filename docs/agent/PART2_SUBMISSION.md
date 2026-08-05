# Part 2 submission — Tools Outside the RAG

**Branch:** `cursor/langgraph-agent-tools-b1ec`  
**PR:** https://github.com/Rickycastro1940/ai-engineering-company-project-monorepo/pull/19  
**Label:** `part-2-external-tools`

## Auth note

`GET /api/incidents` and `GET /api/incidents/{id}` currently require **no authentication**.
Optional `INCIDENT_API_TOKEN` / `INCIDENT_API_KEY` are forwarded as Bearer if set.

## Artifacts

| Artifact | Path |
|----------|------|
| Tool-run trace (mocked HTTP shape) | [`docs/agent/part2-tool-run-trace.json`](part2-tool-run-trace.json) |
| **Live** tool-run (real `GET /api/incidents/{id}`) | [`docs/agent/part2-live-tool-run-trace.json`](part2-live-tool-run-trace.json) |
| RAG-run trace | [`docs/agent/part2-rag-run-trace.json`](part2-rag-run-trace.json) |
| Eval output | [`docs/agent/part2-eval-output.txt`](part2-eval-output.txt) |

### Live tool-run (incident manager HTTP)

- Question: status of ticket `BRS-000002`
- Tool called live `GET http://127.0.0.1:8000/api/incidents/BRS-000002` (no mocked ticket rows)
- `node_order`: `receive_question` → `decide_route` → `lookup_ticket` → `answer_ticket`
- `sources_used`: `["ticket"]`
- Answer fields match `scripts/incidents-COMPANY.csv` (`ABIERTO`, `ABASTECIMIENTO`, …)

### Tool-run (ticket source)

- Question: status of ticket `BRS-000002`
- `node_order`: `receive_question` → `decide_route` → `lookup_ticket` → `answer_ticket`
- `sources_used`: `["ticket"]`

### RAG-run (knowledge base)

- Question: minimum stock rule for proteins
- `node_order`: `receive_question` → `decide_route` → `retrieve` → `generate`
- `sources_used`: `["rag"]`

### Evals

```text
27 passed  (test_agent_tools.py + test_agent_graph.py)
42 passed  (full tests/pipelines/)
```

## Typed contract

- **Input:** `TicketLookupInput` — `ticket_id` or filters (`status`, `category`, `location_id`, `date_from`, `date_to`)
- **Output:** `TicketRecord` — `incident_id`, `date`, `location_id`, `category`, `description`, `status`, `customer_id`, `satisfaction_score`, `reporter_id`, `source` (same fields as the incident API)
