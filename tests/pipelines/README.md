# Pipeline / agent evals

Agent (LangGraph Part 1) and other pipeline evals live here.

## Support agent evals — single command

```bash
uv run pytest tests/pipelines/test_agent_graph.py -q
```

These evals assert against **saved traces** (and mocked retrieve/generate), not a
live LLM/Qdrant call every time.

| Eval | Criterion |
|------|-----------|
| `test_eval_retrieve_runs_before_generate` | `retrieve` runs before `generate` in the trace |
| `test_eval_empty_question_skips_retrieve` | empty input never retrieves |
| `test_eval_no_context_when_retrieve_empty` | no chunks → `no_context`, not forced generate |
| `test_eval_answer_grounded_in_context_knowledge_base` | answer cites CONTEXT / supplier-ordering facts (3 days protein, Lucía Fernández) |
| `test_every_run_produces_queryable_trace` | JSON trace has node order + outputs on disk |
| `test_checkpointing_persists_thread_state` | MemorySaver history has ≥3 transitions |

Grounding is an acceptance gate — a perfect trace with an ungrounded answer fails.
