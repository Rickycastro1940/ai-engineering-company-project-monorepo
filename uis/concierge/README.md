# Guest concierge page

Static page for the Brasaland guest concierge. The central API serves it at `GET /concierge/` (`uis/concierge/index.html` and `concierge.js`). There is no separate dev server or package.

The page opens `WS /concierge/ws`, appends `token_chunk` text, and can send `interrupt`. A voice file is posted to `POST /concierge/transcribe` first. With no `BRASALAND_AUDIO_API_KEY`, type the order.

```bash
NO_SALES_MONITOR=0 python3 -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/concierge/`.
