# `data/pipelines` folder

This folder groups **all data pipelines in the monorepo** related to the company: ingestion, ETL/ELT, cleaning, transformation, and loading into analytical or production systems.

Each subfolder or file under `data/pipelines/` should represent **one pipeline or job set** (for example `sales-etl`, `telemetry-stream`, `customer-segmentation`) and include the required configuration (scripts, orchestration, connectors, schemas, etc.).

- **Main purpose**: consolidate in one place the data movement and transformation logic that powers the company’s applications and analytics.
- **Recommendation**: document pipelines as you add them—their goal, data sources and sinks, dependencies, and how to run them in development, testing, and production.

## Brasaland RAG (`rag.py`)

Course contract — all four entry points are importable from `data.pipelines.rag`:

| Function | Role |
|----------|------|
| `setup` | Index `docs/company-knowledge-base/` into Qdrant (`brasaland_kb`) |
| `embed` | Embed a text string (shared embedding client) |
| `retrieve` | Embed query → search Qdrant → filter by `min_score` |
| `query` | Monolithic retrieve + generate (legacy `/knowledge/query`) |
| `generate_answer` | Generation-only step for the LangGraph agent (Part 1) |

`setup` / `embed` are implemented in `data/process/rag.py` and re-exported here so indexing logic is not duplicated. The LangGraph agent in `services/agent/` calls `retrieve` and `generate_answer` as separate nodes — never the monolithic `query()` inside one node.

HTTP adapters:

- `POST /knowledge/query` → `services/api/routers/knowledge.py`
- `POST /agent/query` → `services/agent/router.py`

> _Spanish version: [README.es.md](./README.es.md)._
