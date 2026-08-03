# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

## RAG helpers

| Script | Purpose |
|--------|---------|
| [`smoke_index_rag.py`](./smoke_index_rag.py) | Offline Qdrant smoke index with deterministic fake embeddings (no 4Geeks key). Prefer `uv run python data/process/rag.py` when a real `sk-…` key is available. |
| [`check_qdrant_connectivity.py`](./check_qdrant_connectivity.py) | Ping local Qdrant |
| [`rag.py`](./rag.py) | Thin CLI shim → `data.pipelines.rag` |

> _Spanish version: [README.es.md](./README.es.md)._
