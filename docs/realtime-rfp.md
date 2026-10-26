# Live RFP registration

Department: **Marketing and Digital Experience** (Camila Ospina) — she opens the ticket when a corporate catering, concession, or co-branding request arrives. **Technology** (Nicolás Park) — the stream sits on the central API. Felipe Guerrero, Lucía Fernández, and Jake Morrison see the same ticket while it is `analyzing`.

The staff console (`uis/backoffice`) subscribes with the staff JWT. `/accessible` is the operations dashboard (locations, inventory, no-sales). A new registration appears there as a Corporate RFP notice without reloading the page and without reloading locations or inventory. `/rfp-intake` is the registration form and the full ticket list.

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

`GET /notifications/stream` sends `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, a `: keep-alive` comment, then `id` / `event: rfp_ticket_created` / `data`. Each payload includes `event_id`.

Recovery, documented here: the browser sends `Last-Event-ID` and the server replays newer tickets. On reconnect the dashboard also refetches `GET /rfp/tickets` and merges by `ticket_id`, so a ticket registered during the gap is not dropped and is not shown twice. The operations dashboard opens the stream after that snapshot, using the highest `event_id` as the first cursor, so older tickets stay in the list and only a later registration is marked **New RFP**.

The console uses `fetch` and `ReadableStream` (`response.body.getReader()`) with `Authorization: Bearer`. It does not use `EventSource`. Reconnect waits 1s, 2s, 4s, 8s, 16s, then 30s. The intake form loads `GET /locations/overview` and disables the other market once one restaurant is checked.

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

`test_http_stream_frames_named_rfp_ticket_created_event` reads `GET /notifications/stream` and checks `Content-Type: text/event-stream`, the `event: rfp_ticket_created` line, and a `data:` JSON object with the Brasaland RFP fields (`ticket_id`, `status: analyzing`, client site, restaurants, COP or USD).

`test_reconnect_recovers_ticket_registered_while_disconnected` closes that stream, registers a ticket during the gap, and opens it again with `Last-Event-ID`. The missed ticket is the only `rfp_ticket_created` frame. The UI test `recovers a ticket missed during the backoff without a second card` checks the 1s then 2s wait and that a replay plus a snapshot still has one row per `ticket_id`.
