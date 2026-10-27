# Manager support over WebSocket

Department: **Operations** (Felipe Guerrero — location managers ask the support agent) and **Training** (Jake Morrison — the standards the answer cites). **Technology** (Nicolás Park) hosts the socket on the central API. **Executive** (Mariana Restrepo) can use the same thread.

The agent id is `manager_support`. It answers through the existing `POST /knowledge/query` path (`data.pipelines.rag`). It is retrieval plus a completion, not a LangGraph graph. Token delivery follows LangGraph `stream_mode="messages"`: one text delta at a time. `values` and `updates` are whole-node snapshots and are not sent.

`POST /knowledge/query` is unchanged: one question, one `answer`.

## Session

Create a thread first. The socket does not create one.

`POST /knowledge/sessions` with the staff JWT returns `session_id` `BRS-CHAT-000001`, the same value as `thread_id`, `company: brasaland`, `agent_id: manager_support`, `status: idle`, `messages: []`, and `draft: ""`.

Connect:

`WS /knowledge/ws?token=...&session_id=BRS-CHAT-000001`

`thread_id` is an alias of `session_id`. A missing JWT closes `4401` before any chat event. An unknown id closes `4404`. Several sockets may subscribe to the same session. Closing one of them leaves the turn running. Reconnect with the same id restores messages on `support_session`.

The page waits 1s, then 2s, 4s, and so on up to 30s before it opens the socket again. That wait is `reconnectDelayMs` in `uis/knowledge/reconnect.js`.

## Events

Client: `support_auth` (`token`), `support_user_message` (`content`), `interrupt` (optional `new_input` starts a new turn after the stop).

Server: `support_session`, `token_chunk` (`delta`), `generation_interrupted` (`content`, `status: interrupted`, optional `new_input`), `generation_completed` (`content`, `status: complete`), `support_error` (`detail`).

`interrupt` cancels the turn task and closes the model stream. No further `token_chunk` frames belong to that generation. The partial assistant text stays on the thread. When `new_input` is set, the next `generation_completed` answers that text as a new turn. There is no generic `message` event and no Part 1 RFP event on this socket.

Generation publishes to an in-memory hub. The socket only forwards. Redis is not required.

## Run

```bash
JWT_SECRET_KEY=brasaland-dev-secret NO_SALES_MONITOR=0 \
  python3 -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/knowledge/`, sign in with a staff email and password, and ask a standards question. Tokens append to the live bubble. The finished frame does not replace that text. **Stop reply** sends `interrupt`. Sending another question while tokens are still arriving sends `interrupt` with `new_input`: the partial bubble stays, marked Interrupted, and the new answer is a separate bubble. A dropped connection waits 1s, 2s, 4s, up to 30s, then opens the same `session_id` and `thread_id`. The page restores `support_session.messages` before it appends any new `token_chunk`. A reload keeps that id in `sessionStorage` under `brasaland-manager-support-session`.

```bash
NO_SALES_MONITOR=0 python3 -m pytest tests/test_websocket_chat.py tests/test_knowledge_query.py -q
node --test tests/test_chat_reconnect_delay.mjs
```
