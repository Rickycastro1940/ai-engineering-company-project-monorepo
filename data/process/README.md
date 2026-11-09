# `data/process` folder

This folder contains **processed/intermediate data** and/or artifacts produced by pipelines (for example: clean datasets, features, aggregates, intermediate tables, or transformation outputs).

- **Main purpose**: clearly separate “raw” data from data ready for analysis, modeling, or app consumption.
- **Recommendation**: document which pipeline produces each artifact, its schema, refresh cadence, and how quality is validated (checks, constraints, data tests).

## Knowledge index

`rag.py` chunks `docs/company-knowledge-base/` for the retrieval pipeline in `data/pipelines/rag.py`. `setup()` with `BRASALAND_RAG_BACKEND=qdrant` recreates collection `brasaland_kb` with named vectors `dense` (cosine) and `bm25` (term counts, IDF applied by Qdrant). The default setup stays in memory and does not call Qdrant.

> _Spanish version: [README.es.md](./README.es.md)._
