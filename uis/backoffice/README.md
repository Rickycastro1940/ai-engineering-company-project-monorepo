# Brasaland backoffice

Internal staff console for **Brasaland Digital** (see root [`CONTEXT.md`](../../CONTEXT.md)).

**Layout is separate from** [`uis/website`](../website/) (public marketing site).

## Routes

| Path | Purpose |
| --- | --- |
| `/accessible` | Welcome / entry dashboard — loads company location footprint from the API |
| `/` | Redirects to `/accessible` |

## Company data (visible in UI)

`GET /locations/overview` returns **14** locations across **Colombia** and **Florida**, with **COP** and **USD** — facts from `CONTEXT.md`, implemented in `services/api/locations.py`.

## Run

```bash
# Terminal 1 — API (monorepo root)
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — backoffice
cd uis/backoffice
npm install
npm run dev
```

Open `http://localhost:5174/accessible`.

Legacy static KPI/telemetry HTML (pre-Vite) is under `legacy/`.
