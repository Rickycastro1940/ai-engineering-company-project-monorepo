# Pipeline / agent evals

Agent (LangGraph Part 1) and RAG pipeline evals live here.

## Single command (agent + RAG evals)

```bash
uv run pytest tests/pipelines/ -q
```

(`test_pipeline.py` is ignored here — it needs optional Supabase/Prefect deps unrelated to Part 1.)

Agent-only:

```bash
uv run pytest tests/pipelines/test_agent_graph.py -q
```

Evals assert against **saved traces** (mocked retrieve/generate) — not a live
LLM/Qdrant call every time. Grounding remains an acceptance gate.

| Eval | Criterion |
|------|-----------|
| `test_eval_retrieve_runs_before_generate` | `retrieve` before `generate` in the **trace** |
| `test_eval_empty_question_skips_retrieve` | empty input never retrieves |
| `test_eval_no_context_when_retrieve_empty` | no chunks → `no_context` |
| `test_eval_answer_grounded_in_context_knowledge_base` | answer cites **CONTEXT-company.md** facts (3 days, Lucía Fernández, 500 USD) |
| `test_eval_grounding_from_saved_trace_artifact` | same grounding checks on a saved JSON trace (no live run) |
| `test_every_run_produces_queryable_trace` | JSON trace on disk with node order + outputs |
| `test_rag.py` | existing RAG retrieve/`query`/`generate_answer` unit tests still pass |
