# `data/eval` folder

This folder is for **evaluation and validation**: evaluation datasets, golden sets, experiment results, metrics, and artifacts used to measure quality for models, RAG, agents, or pipelines.

- **Main purpose**: centralize evaluation inputs and outputs so improvements stay measurable across project milestones.
- **Recommendation**: document each evaluation set (what it measures, how it was built, success criteria) and avoid sensitive data; use synthetic or anonymized data when needed.

## Brasaland RAG

- [`rag-golden-set.md`](./rag-golden-set.md) — 15 question / expected-source pairs for retrieval regression after indexing `brasaland_kb`.

> _Spanish version: [README.es.md](./README.es.md)._
