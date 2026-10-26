# `data/pipelines` folder

This folder groups **all data pipelines in the monorepo** related to the company: ingestion, ETL/ELT, cleaning, transformation, and loading into analytical or production systems.

Each subfolder or file under `data/pipelines/` should represent **one pipeline or job set** (for example `sales-etl`, `telemetry-stream`, `customer-segmentation`) and include the required configuration (scripts, orchestration, connectors, schemas, etc.).

- **Main purpose**: consolidate in one place the data movement and transformation logic that powers the company’s applications and analytics.
- **Recommendation**: document pipelines as you add them—their goal, data sources and sinks, dependencies, and how to run them in development, testing, and production.

## Public site snapshot

`public_site_snapshot.py` reads Brasaland's own static pages on `https://www.brasalandrestaurant.com` (home, menu, locations, Brasa Points, allergens). It writes JSON Lines and SQLite for Marketing's guest copy and a later knowledge load. It does not crawl other sites, log in, or replace `pipeline.py` (the weekly location cost and waste load).

Location ids in this snapshot are the labels printed on the public locations page. They are not the 14 `Location.id` values in `services/api/locations.py`.

```bash
python3 -m data.pipelines.public_site_snapshot \
  --jsonl data/raw/public_site_snapshot.jsonl \
  --sqlite data/raw/public_site_snapshot.sqlite3
```

> _Spanish version: [README.es.md](./README.es.md)._
