# `data/process` folder

This folder contains **processed/intermediate data** and artifacts produced by pipelines.

## Brasaland RAG indexer

Index the company knowledge base into Qdrant:

```bash
# Prerequisites: docker compose up -d qdrant  +  real keys in root .env
uv run python data/process/rag.py
```

Expect **38** semantic chunks in collection `brasaland_kb` (see `CONTEXT.md` / `CONTEXT-company.md`).

Offline smoke (no 4Geeks key; deterministic fake vectors — not for evaluation):

```bash
uv run python scripts/smoke_index_rag.py
```

> _Spanish version: [README.es.md](./README.es.md)._
