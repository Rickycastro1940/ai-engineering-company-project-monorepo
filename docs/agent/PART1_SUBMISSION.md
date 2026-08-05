# Part 1 of 2 — Submission

**PR:** https://github.com/Rickycastro1940/ai-engineering-company-project-monorepo/pull/18  
**Branch:** `cursor/langgraph-agent-migration-b1ec`  
**Label:** `part-1-langgraph`

## Required structure

```text
data/pipelines/     ← RAG functions reused
services/agent/     ← LangGraph graph, nodes, endpoint
tests/pipelines/    ← agent evals
```

## Required PR artifacts

### 1. Screenshot / export of a full-run trace

- **Screenshot:** [`full-run-trace-screenshot.png`](./full-run-trace-screenshot.png)
- **JSON export:** [`full-run-trace.json`](./full-run-trace.json)
- Also: `data/process/agent-traces/sample-grounding-eval.json`

Nodes for this run: `receive_question` → `retrieve` → `generate`  
Question: minimum protein stock rule · Answer grounded in supplier-ordering / Lucía Fernández / 3 days / 500 USD

### 2. Output of running the evals

- **Console file:** [`eval-output.txt`](./eval-output.txt)
- Command: `uv run pytest tests/pipelines/ -v --tb=no`
- Result: **28 passed**
