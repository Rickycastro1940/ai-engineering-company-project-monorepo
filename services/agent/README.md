# `services/agent` — Brasaland Support Agent (LangGraph Part 1)

LangGraph migration of the existing Brasaland RAG flow. Retrieval and generation
stay in `data/pipelines/rag.py`; this service only orchestrates them as an
explicit, checkpointed, traceable graph.

## Graph

```text
START → receive_question ──(empty?)──► empty_question → END
                 │
                 └──(ok)──► retrieve ──(no chunks)──► no_context → END
                                 │
                                 └──(chunks)──► generate → END
```

| Node | Responsibility |
|------|----------------|
| `receive_question` | Normalize/validate the question |
| `retrieve` | Calls `data.pipelines.rag.retrieve` |
| `generate` | Calls `data.pipelines.rag.generate_answer(question, context)` |
| `no_context` | Honest "not enough information" when nothing clears the score threshold |
| `empty_question` | Clear error path for blank input |

Edges are **conditional** (empty question → error; no retrieval hits → no_context).
The graph is **compiled once** at startup with a `MemorySaver` checkpointer.

## API

```bash
# Preferred — standalone agent service
uv run uvicorn services.agent.app:app --reload --port 8000

# Or via the main company API (agent router is mounted there too)
uv run uvicorn api.app:app --reload --port 8000

# Query the agent
curl -s -X POST http://127.0.0.1:8000/agent/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the minimum stock rule for proteins?"}'

# Load a saved trace
curl -s http://127.0.0.1:8000/agent/traces/<trace_id>
```

Traces are also written to `data/process/agent-traces/<trace_id>.json`.

## Evals

```bash
uv run pytest tests/pipelines/test_agent_graph.py -q
```
