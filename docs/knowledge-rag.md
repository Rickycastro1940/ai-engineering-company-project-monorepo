# Brasaland knowledge RAG

Department: **Training** (Jake Morrison — one searchable standard for recipes, waste, allergens, and ordering) and **Executive** (Mariana Restrepo — a question she can ask without calling a manager). The route sits on the **Technology** central API.

## One path

| Step | Module | Role |
| --- | --- | --- |
| Sources | `docs/company-knowledge-base/*.md` | Allergen guide, waste protocol, supplier ordering, Brasa Points |
| Index | `data/process/rag.py` | Paragraph chunks, collection name `brasaland_kb` |
| Retrieve + answer | `data/pipelines/rag.py` | Top chunks, then an answer that stays inside those chunks |
| HTTP | `services/knowledge/routes.py` | `POST /knowledge/query` |
| App | `services/api/app.py` | Loaded by `uvicorn api.app:app` |

`scripts/rag.py` is deprecated. It searched collection `company_knowledge_base` with a generic sales prompt, so it did not read the index `data/process/rag.py` wrote. It now delegates to `data.pipelines.rag`.

`services/api/main.py` is deprecated. It imported a missing `api.routers.knowledge` module. Running it starts the central app.

`services/api/uis/pages/knowledge.js` is not mounted in `uis/website` or `uis/backoffice`. Staff call the HTTP route.

## Request and response

```bash
curl -sS -X POST http://127.0.0.1:8000/knowledge/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What allergens are in the House Sauce?"}'
```

```json
{
  "answer": "Source: brasaland-menu-allergens.en.md (...)\n...",
  "sources": [
    {
      "source_document": "brasaland-menu-allergens.en.md",
      "section": "Menu Allergen Guide · part 2",
      "text": "...",
      "score": 0.42,
      "chunk_index": 1,
      "language": "en"
    }
  ]
}
```

Empty or whitespace questions return HTTP 400. A question with no supporting chunk returns the sentence `There is not enough information available to answer this question.` and `"sources": []`. Qdrant or OpenAI failures return HTTP 503 with a generic message (no keys, no host paths).

The route is not behind JWT so a kitchen lead can query standards without the staff console token. Locations and the Monday report stay authenticated.

## Offline by default

Tests and CI do not need `OPENAI_API_KEY` or a Qdrant process.

| Variable | Default | Effect |
| --- | --- | --- |
| `BRASALAND_RAG_BACKEND` | `local` | `qdrant` searches collection `brasaland_kb` (dense + BM25 sparse) |
| `BRASALAND_RAG_EMBEDDINGS` | `local` | `openai` uses `text-embedding-3-small` (1536-d) when indexing or querying Qdrant |
| `BRASALAND_RAG_LLM` | `extractive` | `openai` calls a chat model (`BRASALAND_RAG_LLM_MODEL`, default `gpt-4o-mini`) |
| `BRASALAND_RAG_RERANK` | (auto) | `cohere` when `COHERE_API_KEY` is set, otherwise a local cross-encoder. `local` forces the offline scorer. `cohere` with no key also falls back to local |
| `COHERE_API_KEY` | unset | Cohere Rerank. Never commit a value. The pipeline answers without it |
| `COHERE_RERANK_MODEL` | `rerank-v3.5` | Used only when the Cohere reranker runs |
| `COHERE_RERANK_URL` | `https://api.cohere.com/v2/rerank` | Override for a compatible rerank endpoint |
| `OPENAI_API_KEY` | unset | Required only for the openai embedding or llm modes |
| `OPENAI_BASE_URL` | unset | Optional compatible endpoint |
| `QDRANT_HOST` / `QDRANT_PORT` | `localhost` / `6333` | Used only when backend is `qdrant` |
| `BRASALAND_KNOWLEDGE_DIR` | `docs/company-knowledge-base` | Corpus directory |

Local mode hashes tokens into a 384-d vector (SHA-256 buckets, L2-normalised) and ranks chunks with token overlap (0.75) plus cosine (0.25). Chunks scoring under 0.30 are dropped, then the cross-encoder reorders that shortlist. Qdrant mode runs a hybrid query: named vector `dense` (cosine) and named sparse vector `bm25` (term counts, `Modifier.IDF`), fused with reciprocal rank fusion. Fusion scores are scaled so the best hit is 1.0. Hits under 0.40 are dropped. A wider candidate pool (4×k) is re-ranked before the top k are returned. An older dense-only collection is still searched with cosine until it is reindexed.

The cross-encoder is Cohere Rerank when `COHERE_API_KEY` is set. With no key, a local pairwise scorer (token overlap, in-order coverage, BM25, and cosine when a vector is already on the chunk) runs in-process. No Cohere SDK is required. The answer quotes the retrieved paragraphs and names the file. Currency figures stay as written (COP and USD). The prompt used for the optional model forbids “zero risk” / “100% safe” on allergens and forbids inventing quantities.

`qdrant-client` is imported only when `BRASALAND_RAG_BACKEND=qdrant`. It is not required for the default path. Reindex after this hybrid schema (the setup step deletes `brasaland_kb` and recreates `dense` + `bm25`). Index with the same embedding mode you will query:

```bash
BRASALAND_RAG_BACKEND=qdrant BRASALAND_RAG_EMBEDDINGS=openai \
  OPENAI_API_KEY=... python -m data.process.rag
```

Local index build (no network):

```bash
python -m data.process.rag
```

## Golden set

`data/eval/knowledge_qa.jsonl` holds questions grounded in the four knowledge files. `data/eval/eval_knowledge_qa.py` prints retrieval hit rate (expected file in `sources`) and answer checks (`must_include` / `must_not_include` against the answer text). The script forces the local/extractive path so a key in the environment does not change the score.

```bash
python data/eval/eval_knowledge_qa.py
python -m pytest tests/test_knowledge_query.py -q
```

Brasa Points copy in the knowledge file matches `CONTEXT.md`: physical stamp cards, no digital app yet. Earn and redeem amounts stay in COP and USD as written.
