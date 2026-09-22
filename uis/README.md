# `uis` folder

This folder contains **all projects with a user interface** for the cross-functional AI Engineering company project — for example: a public website, admin dashboard frontend, ecommerce UI, customer portals, Streamlit/Gradio app or other frontend-only tools.

The two main projects stored here are:

- **`website`** — Brasaland’s public-facing corporate site (Vite + React). Home route `/`. See [`website/README.md`](./website/README.md).
- **`backoffice`** — internal Brasaland Digital console (Vite + React). Public `/login` and `/register`; staff views (`/`, `/accessible`, `/account/profile`, `/account/change-password`) use a client layout guard (`ProtectedRoute` + `useRequireAuth`) that checks `localStorage` and `GET /auth/me`. See [`backoffice/README.md`](./backoffice/README.md). Legacy static KPI HTML lives in `backoffice/legacy/`.

Also present: **`web/`** — incident-analysis HTML tool (not the public marketing site).

## Docker

[`Dockerfile`](./Dockerfile) uses the official **Node Alpine** image (`node:22-alpine`). It installs npm dependencies for `uis/website` and `uis/backoffice` in **separate** `npm ci` layers, then copies each app’s source. The default command serves the public site on port 5173; run the staff console by setting `working_dir` to `/uis/backoffice` and port 5174.

```bash
# from this folder
docker build -t brasaland-uis .

# public site (Marketing)
docker run --rm -p 5173:5173 brasaland-uis

# staff backoffice (Operations / Executive)
docker run --rm -p 5174:5174 -w /uis/backoffice brasaland-uis \
  npm run dev -- --host 0.0.0.0 --port 5174
```

Root Compose also builds this image for the `website` and `backoffice` services.

Organize `uis/` by **different concerns** — each subfolder covers a distinct area of the company (for example, public web vs internal operations) and includes its own technical and functional documentation.

- **Main purpose**: to centralize in a single place all frontend applications that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the applications you add, their objective, the technology used, and how to run them.

> _Estas instrucciones también están disponibles en [español](./README.es.md)._
