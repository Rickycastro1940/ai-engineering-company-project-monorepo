# Knowledge chat over WebSocket

Department: **Training** (Jake Morrison — the standards the assistant cites) and **Executive** (Mariana Restrepo — a question she can stop if the answer goes the wrong way). **Technology** (Nicolás Park) hosts the socket on the central API.

The assistant is `brasaland_knowledge_assistant`. It reads the `brasaland_kb` collection. It is retrieval plus a completion, not a LangGraph graph. Token delivery follows LangGraph `stream_mode="messages"`: one text delta at a time. `values` and `updates` are whole-node snapshots and are not sent.

`POST /knowledge/query` is unchanged: one question, one `answer`.

## Session

Create a thread first. The socket does not create one.

`POST /knowledge/sessions` with the staff JWT returns `session_id` `BRS-CHAT-000001`, the same value as `thread_id`, `company: brasaland`, `agent_id: brasaland_knowledge_assistant`, `status: idle`, and `messages: []`.

Connect:

`WS /knowledge/ws?token=...&session_id=BRS-CHAT-000001`

`thread_id` is an alias of `session_id`. A missing JWT closes `4401` before any chat event. An unknown id closes `4404`. Disconnect keeps the messages. Reconnect with the same id restores them on `knowledge_session`.

## Events

Client: `knowledge_auth` (`token`), `knowledge_user_message` (`content`), `knowledge_interrupt` (optional `content` starts a new turn after the stop).

Server: `knowledge_session`, `knowledge_token` (`delta`), `knowledge_assistant_message` (`content`, `status` `complete` or `interrupted`), `knowledge_error` (`detail`).

There is no generic `message` event.

## Run

```bash
JWT_SECRET_KEY=brasaland-dev-secret uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/knowledge/ui`, sign in with a staff account, and ask a standards question. **Stop reply** sends `knowledge_interrupt`. **Reconnect** uses the same `BRS-CHAT-` id.

```bash
NO_SALES_MONITOR=0 python3 -m pytest tests/test_websocket_chat.py tests/test_knowledge_query.py -q
```
