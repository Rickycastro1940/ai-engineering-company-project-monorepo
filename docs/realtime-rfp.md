# Live RFP registration

Department: **Marketing and Digital Experience** (Camila Ospina) — she opens the ticket when a corporate catering, concession, or co-branding request arrives. **Technology** (Nicolás Park) — the stream sits on the central API. Felipe Guerrero, Lucía Fernández, and Jake Morrison see the same ticket while it is `analyzing`.

The staff console (`uis/backoffice`, route `/rfp-intake`) subscribes with the staff JWT. A new registration shows up without a reload.

## Event

Registration is `POST /rfp/tickets`. The server assigns `status: analyzing`. Clients cannot set the status. The named SSE event is `rfp_ticket_created`.

Fields on every notification:

| Field | Value |
| --- | --- |
| `ticket_id` | Server id |
| `rfp_id` | `rfp_` plus the ticket id |
| `status` | `analyzing` |
| `company` | `brasaland` |
| `owner` | Camila Ospina |
| `client_name` | Client on the request |
| `location` | Client site as written on the request (Medellín, Florida, …) |
| `locations` | Brasaland restaurants from the 14-location roster. One ticket uses one market |
| `country` | `Colombia` or `United States`, taken from those restaurants |
| `currency` | `COP` or `USD`, taken from those restaurants. The API does not convert |
| `service_type` | Catering, concession, co-branding, or the wording on the request |
| `scope` | Volume: diners, sites, contract length |
| `deadline` | Response deadline, as written |
| `budget_range` | Optional. Must name the ticket currency (`COP` or `USD`) as written |
| `departments_needed` | Any of `marketing`, `operaciones`, `procurement`, `training` |
| `raw_pdf_path` | Stored upload |
| `created_at`, `updated_at` | UTC timestamps |
| `terminal` | `false` while the ticket is analyzing |

## Routes

| Method | Path | Auth |
| --- | --- | --- |
| `POST` | `/rfp/tickets` | Bearer JWT. Multipart file plus the fields above |
| `GET` | `/rfp/tickets` | Bearer JWT. Snapshot for load and reconnect |
| `GET` | `/rfp/tickets/{ticket_id}` | Bearer JWT |
| `GET` | `/notifications/stream` | Bearer JWT. SSE |

Unauthenticated calls return **401**.

`location` is the client site. `locations` is the list of Brasaland restaurants (`id`, `name`, `city`, `country`, `currency`). Mixing a Colombia id with a Florida id returns **400**. A Florida ticket whose budget is written in COP also returns **400**.

`GET /notifications/stream` sends `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, a `: keep-alive` comment, then `id` / `event: rfp_ticket_created` / `data`. `Last-Event-ID` replays newer registrations. The console uses `fetch` and `ReadableStream` because `EventSource` cannot set `Authorization`. Reconnect waits 1s, 2s, 4s, 8s, 16s, then 30s, and refetches `GET /rfp/tickets`. The list keeps one row per `ticket_id`. The intake form loads `GET /locations/overview` and disables the other market once one restaurant is checked.

## Run

```bash
JWT_SECRET_KEY=brasaland-dev-secret uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd uis/backoffice
npm install
npm run dev
```

Open `http://127.0.0.1:5174/login`, sign in, and open **RFP registration**.

## Tests

```bash
NO_SALES_MONITOR=0 python -m pytest tests/test_rfp_sse.py -q
node --experimental-strip-types --test uis/backoffice/tests/rfpNotifications.test.ts
```
