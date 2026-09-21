# Brasaland backoffice

Internal staff console for **Brasaland Digital** (see root [`CONTEXT.md`](../../CONTEXT.md)).

**Layout is separate from** [`uis/website`](../website/) (public marketing site). The public site is not gated by this JWT session.

## Routes

| Path | Purpose | Access |
| --- | --- | --- |
| `/login` | Email + password form. Success stores JWT and opens `/accessible`. Failure stays on the form. | Public |
| `/register` | Registration form. Success: `POST /users` (optional `name`) then `POST /auth/login`, store JWT, open `/accessible`. Failure shows field-level errors. | Public |
| `/accessible` | Welcome dashboard — `GET /locations/overview` | Protected |
| `/inventory` | Kitchen inventory — list/add products, incoming/outgoing stock, low-stock alerts | Protected |
| `/inventory/products` | Kitchen products catalogue from `GET /inventory`, stock-level indicators, inbound/outbound order links | Protected |
| `/inventory/orders/inbound` | Inbound ingredient order form (`POST /inventory/orders/inbound`); product chosen by name | Protected |
| `/inventory/orders/outbound` | Outbound kitchen usage form (`POST /inventory/orders/outbound`); live current stock + insufficient-stock 400 | Protected |
| `/inventory/orders/new` | Create inbound (supplier delivery) or outbound (kitchen usage) order for one product | Protected |
| `/account/profile` | Email plus name/phone/address from `GET /auth/me`; edit contact via `PUT /profiles/me` | Protected |
| `/account/change-password` | Password update via `PUT /users/{id}` | Protected |
| `/` | Redirects to `/accessible` | Protected |

There is **no Next.js app** in this monorepo. Staff views live in this Vite SPA. `uis/website` (public milestone one) is a separate app and must not check a token or redirect to `/login`. `uis/web` is incident HTML, not a session console.

Protected staff views (all of them): `/`, `/accessible`, `/inventory`, `/inventory/products`, `/inventory/orders/inbound`, `/inventory/orders/outbound`, `/inventory/orders/new`, `/account/profile`, `/account/change-password`, and any unmatched path (`*`). Public in this app: `/login`, `/register`.

Unauthenticated or **invalid** sessions redirect to `/login?next=…`. Logout clears `localStorage` (`auth_token`) and returns to `/login`. `GET /locations` and `GET /locations/overview` require a Bearer token. The operations page also loads `GET /inventory` with that header. Full kitchen inventory management lives at `/inventory` (`POST /inventory`, `PATCH /inventory/{id}`, `GET /inventory/alerts`). All of those calls go through `src/lib/inventory.ts` — pages never call `fetch` for inventory. 4xx/5xx responses surface `message`/`detail` from the API body.

## Authentication

Client-side JWT session (the usual Next.js layout-guard pattern, implemented here in Vite — **no middleware**, because the token is only in `localStorage`, not a cookie):

1. After `POST /auth/login` returns `access_token`, store it in `localStorage` as `auth_token` and redirect to `/accessible`. Registration does the same after `POST /users` then `POST /auth/login`.
2. On every protected `fetch`, read that key and set `Authorization: Bearer <token>` (`apiRequest` in `src/lib/api.ts`; kitchen inventory uses `src/lib/inventory.ts`).
3. Protect routes with a **client layout guard** (`ProtectedRoute` + `useRequireAuth`). The hook reads `localStorage` and, when a token is present, `AuthProvider` validates it with `GET /auth/me`. Missing or invalid tokens redirect to `/login`.
4. Logout removes `auth_token` from `localStorage` and redirects to `/login`.
5. A **401** on a protected API call (including `GET /auth/me`) removes the token and redirects to `/login`. Failed login/register stay on the form.

Register validation errors (422 loc/msg, or 409 duplicate email) are shown next to the matching field.

Set `JWT_SECRET_KEY` before starting the API so tokens survive uvicorn reloads.

## Run

```bash
# Terminal 1 — API (monorepo root)
JWT_SECRET_KEY=brasaland-dev-secret uvicorn api.app:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — backoffice
cd uis/backoffice
npm install
# Inventory API base (Vite loads .env.local; this is not a Next.js app)
# NEXT_PUBLIC_INVENTORY_API_URL=http://localhost:8000
npm run dev
```

Open `http://localhost:5174/login`. Vite proxies `/auth`, `/users`, `/profiles`, `/locations`, `/inventory`, and `/api` to `http://127.0.0.1:8000`. Kitchen inventory calls also use `NEXT_PUBLIC_INVENTORY_API_URL` when that file is present.

Legacy static KPI/telemetry HTML (pre-Vite) is under `legacy/`.
