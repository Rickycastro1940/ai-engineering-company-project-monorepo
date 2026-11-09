# Guest concierge

Department: **Marketing** (Camila Ospina — a guest can ask the menu and place an order), **Restaurant Operations** (Felipe Guerrero — the order names one of the 14 kitchens and the currency that kitchen charges), and **Technology** (Nicolás Park — the stream sits on the central API).

The concierge reads the chain menu from `services/api/menus.py` and the location roster from `services/api/locations.py`. It does not copy those prices into a second catalogue. A placed order is a guest ticket for the kitchen. It is not written to `POST /sales` and it does not clear a no-sales alert.

## Streams

| Path | Transport | What it does |
| --- | --- | --- |
| `WS /concierge/ws?session_id=` | WebSocket | Same token events as `WS /knowledge/ws`: `token_chunk`, `interrupt`, `generation_completed`, `generation_interrupted` |
| `GET /realtime/concierge/stream?session_id=` | SSE | Same frame shape as `GET /realtime/ops-alerts/stream`: `id`, `event`, `data`, `Last-Event-ID`, keep-alive comments |

`POST /concierge/sessions` opens `BRS-GUEST-…`. The menu is public, so this thread does not use a staff JWT. `GET /concierge/orders` does: Felipe's list of placed orders requires the same Bearer token as the rest of the staff API.

The page is `GET /concierge/`.

## Voice

`POST /concierge/transcribe`

| Env | Role |
| --- | --- |
| `BRASALAND_AUDIO_API_KEY` | When set, audio is sent to the model. When unset, no network call is made. |
| `BRASALAND_AUDIO_MODEL` | Model name. Default `whisper-1`. |
| `BRASALAND_AUDIO_BASE_URL` | OpenAI-compatible base. Default `https://api.openai.com/v1`. |

Without a key, send `{"text": "Two grilled sirloin at Medellín Centro"}`. The response is `mode: text_fallback`. Audio bytes without a key return an empty transcript and the same fallback, and the guest types the order instead.

```bash
NO_SALES_MONITOR=0 python3 -m pytest tests/test_concierge.py -q
```
