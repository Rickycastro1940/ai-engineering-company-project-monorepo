# Support agent (LangGraph)

Department: **Training** (Jake Morrison — the same standards search, with each decision visible) and **Executive** (Mariana Restrepo — one natural-language question, plus a trace of how it was answered). The route is on the **Technology** central API.

`POST /agent/query` invokes a graph compiled at import. Nodes call `retrieve` and `generate_answer` in `data/pipelines/rag.py`. They do not call `query()`, which would retrieve again.

| Node | When it runs |
| --- | --- |
| `receive_question` | Every request. An empty question stops the graph. |
| `retrieve` | Non-empty question. Calls `retrieve()`. |
| `query` | At least one chunk cleared the score threshold. Calls `generate_answer(question, context)`. |
| `honest_answer` | Retrieval returned nothing above the threshold. States that there is not enough information. |

`GET /agent/traces/{trace_id}` returns the steps for that run (node order and a checkpoint id). `POST /knowledge/query` is unchanged.

```bash
curl -sS -X POST http://127.0.0.1:8000/agent/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What allergens are in the House Sauce?"}'
```
