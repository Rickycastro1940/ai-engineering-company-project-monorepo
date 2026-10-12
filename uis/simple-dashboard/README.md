# Simple Dashboard (Tailwind CSS v4)

Academy deliverable: **A simple Dashboard with Tailwind CSS**. Static HTML + Tailwind v4 CDN + `styles.css` media queries for phone / tablet / desktop.

This folder is the resubmission that adds the missing middle **performance drivers** block and a **KPI section heading**. It can also be copied into the standalone submission repo `Rickycastro1940/simple-dashboard-tailwind` if graders expect that URL.

## Layout (three blocks)

1. **Key performance indicators** — four outcome KPI cards under a clear `h2`
2. **Performance drivers** — three widgets (sales by channel, top products, fulfillment funnel)
3. **Operational details** — recent orders table + team notes

## Run

```bash
cd uis/simple-dashboard
pip3 install flask
python3 server.py
```

Open `http://localhost:3000/`.

| File | Role |
| --- | --- |
| `index.html` | Full semantic structure + Tailwind v4 utilities |
| `styles.css` | Layout helpers and `@media` at `640px`, `1024px`, `1280px` |
| `server.py` | Local static server from the html-hello template |

Uses `@tailwindcss/browser@4` (not the legacy v3 `cdn.tailwindcss.com` snippet).
