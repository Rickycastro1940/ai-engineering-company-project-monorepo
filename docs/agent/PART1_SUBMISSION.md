# Part 1 of 2 — Submission

**PR:** https://github.com/Rickycastro1940/ai-engineering-company-project-monorepo/pull/18  
**Branch:** `cursor/langgraph-agent-migration-b1ec`  
**Label:** `part-1-langgraph`  
**Base:** `main` (independent from Part 2)

## Required structure

```text
data/
  pipelines/          ← setup/embed/retrieve/query (+ generate_answer), reused
services/
  agent/              ← LangGraph state, nodes, graph, endpoint
tests/
  pipelines/          ← agent + RAG evals
```

## Required artifacts

1. **Full-run trace export:** [`full-run-trace.json`](./full-run-trace.json)  
   Also: `data/process/agent-traces/sample-grounding-eval.json`
2. **Eval console output:** [`eval-output.txt`](./eval-output.txt)  
   Command: `uv run pytest tests/pipelines/ -q` → **28 passed**

## Checkpoint sample

`data/process/agent-traces/sample-checkpoint-history.json`
