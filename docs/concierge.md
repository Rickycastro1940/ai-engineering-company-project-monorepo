# Guest concierge

Marketing (Camila Ospina) and Restaurant Operations (Felipe Guerrero). Technology hosts it on `uvicorn api.app:app`.

Guests ask for the dual-currency menu, an allergen, or an order at one of the 14 locations. Prices and allergens come from `GET /menus`. The kitchen name and its currency come from the location roster (`COP` in Colombia, `USD` in Florida). Both list prices are shown on every answer that names a dish.

A confirmed order is stored for `GET /concierge/orders` (staff JWT). It is not a POS ticket.

## WebSocket

Create a session, then connect. The socket does not create one.

`POST /concierge/sessions` → `session_id` `BRS-GUEST-…`, `agent_id: guest_concierge`.

`WS /concierge/ws?session_id=BRS-GUEST-…`

Client frames: `concierge_user_message` (`content`), `interrupt` (optional `new_input`).

Server frames: `concierge_session`, `token_chunk` (`delta`), `generation_completed`, `generation_interrupted`, `concierge_order`, `concierge_error`.

An unknown id closes `4404`. Several sockets can share one session. `interrupt` stops further `token_chunk` frames for that turn. This is the same bidirectional idea as `WS /knowledge/ws`: the person watching the tokens can stop them on that socket. SSE cannot carry `interrupt`.

## SSE

`GET /realtime/concierge/stream?session_id=BRS-GUEST-…`

Named events, a keep-alive comment, and `Last-Event-ID` replay — the same shape as `GET /realtime/ops-alerts/stream`. The no-sales stream is unchanged and still requires a staff JWT. The concierge stream is one guest thread and does not require a JWT because the menu is already public. Pass `Last-Event-ID: 0` to replay tokens from a turn that already finished.

`POST /concierge/sessions/{session_id}/messages` with `{"content": "..."}` runs a turn to completion and publishes those tokens for anyone listening.

## Voice orders

`POST /concierge/transcribe`

Set `BRASALAND_AUDIO_API_KEY` (and optionally `BRASALAND_AUDIO_MODEL`, `BRASALAND_AUDIO_BASE_URL`) to send the clip to an OpenAI-compatible `/audio/transcriptions` endpoint. With no key, the route accepts the typed order and does not call the model (`mode: text_fallback`).

The page at `GET /concierge/` sends the transcript over the WebSocket.

```bash
NO_SALES_MONITOR=0 python3 -m pytest tests/test_concierge.py -q
```
