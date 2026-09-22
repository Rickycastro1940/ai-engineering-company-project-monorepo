# `uis` folder

This folder contains **all projects with a user interface** for the cross-functional AI Engineering company project — for example: a public website, admin dashboard frontend, ecommerce UI, customer portals, Streamlit/Gradio app or other frontend-only tools.

The two main projects stored here are:

- **`website`** — Brasaland’s public-facing corporate site (Vite + React). Home route `/`. See [`website/README.md`](./website/README.md).
- **`backoffice`** — internal Brasaland Digital console (Vite + React). Public `/login` and `/register`; staff views (`/`, `/accessible`, `/account/profile`, `/account/change-password`) use a client layout guard (`ProtectedRoute` + `useRequireAuth`) that checks `localStorage` and `GET /auth/me`. See [`backoffice/README.md`](./backoffice/README.md). Legacy static KPI HTML lives in `backoffice/legacy/`.

Also present: **`web/`** — incident-analysis HTML tool (not the public marketing site).

## Docker

[`Dockerfile`](./Dockerfile) uses the official **Node Alpine** image (`node:22-alpine`). It installs npm dependencies for `uis/website` and `uis/backoffice` in **separate** `npm ci` layers, builds both Next.js apps, then the default **CMD** runs [`start.sh`](./start.sh) so both processes start: website on **3000**, backoffice on **3001**. [`.dockerignore`](./.dockerignore) excludes `node_modules`, `.next`, `.env*`, and `*.log`.

```bash
# from this folder
docker build -t brasaland-uis .
docker run --rm -p 3000:3000 -p 3001:3001 brasaland-uis
```

- Public site (Marketing): http://localhost:3000/
- Staff backoffice (Operations / Executive): http://localhost:3001/login

Root [`docker-compose.yml`](../docker-compose.yml) builds **ui** from this folder (bind-mount + `start.sh` / `next dev` on 3000 and 3001) and **backend** from `services/Dockerfile`. They share the named network `brasaland-net`. The backoffice proxy is `API_PROXY=http://backend:8000` (Compose service name, not localhost or a hard-coded IP). Defaults come from committed `.env.example`; no extra copy step is required.

```bash
# from the monorepo root
docker compose up
```

Organize `uis/` by **different concerns** — each subfolder covers a distinct area of the company (for example, public web vs internal operations) and includes its own technical and functional documentation.

- **Main purpose**: to centralize in a single place all frontend applications that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the applications you add, their objective, the technology used, and how to run them.

> _Estas instrucciones también están disponibles en [español](./README.es.md)._
