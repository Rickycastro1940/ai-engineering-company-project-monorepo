# `data/raw` folder

This folder is intended for **raw data** related to the company: dumps, exports, sample files, event samples, or untransformed datasets.

- **Main purpose**: serve as a landing zone or reference for original data before pipelines process it.
- **Recommendation**: document each dataset’s origin, format, expected size, privacy/PII considerations, and how it is versioned (ideally avoiding sensitive data in the repository).

## `brasaland_sales.csv`

Official monthly consolidated sales for the sales-forecast model (120 rows, `2016-01` through `2025-12`). Columns: `month`, `revenue_usd`, `covers_served`, `avg_ticket_usd`, `market` (`consolidated` only). Copied from the course reference file `content/contexts/sales-forecasting/brasaland/brasaland_sales.csv`. Do not regenerate it. Training is `scripts/train_sales_forecast.py`.

> _Spanish version: [README.es.md](./README.es.md)._
