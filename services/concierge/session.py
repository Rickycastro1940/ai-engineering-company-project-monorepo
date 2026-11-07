"""In-memory guest sessions. WebSocket sockets and the SSE stream share one hub."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.concierge.answers import reply, stream_chunks

COMPANY_SLUG = "brasaland"
AGENT_ID = "guest_concierge"
SESSION_ID_PREFIX = "BRS-GUEST-"
EVENT_USER = "concierge_user_message"
EVENT_INTERRUPT = "interrupt"
EVENT_SESSION = "concierge_session"
EVENT_SNAPSHOT = "concierge_snapshot"
EVENT_TOKEN = "token_chunk"
EVENT_INTERRUPTED = "generation_interrupted"
EVENT_COMPLETED = "generation_completed"
EVENT_ERROR = "concierge_error"
EVENT_ORDER = "concierge_order"
WS_CLOSE_NO_THREAD = 4404
HISTORY_LIMIT = 200


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class StreamEvent:
    def __init__(self, event_id: str, event: str, data: dict[str, Any]) -> None:
        self.id = event_id
        self.event = event
        self.data = data

    def encode(self) -> str:
        payload = json.dumps(self.data, separators=(",", ":"), default=str)
        return f"id: {self.id}\nevent: {self.event}\ndata: {payload}\n\n"


class ConciergeStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._placed: list[dict[str, Any]] = []

    def reset(self) -> None:
        self._sessions.clear()
        self._placed.clear()

    def create(self) -> dict[str, Any]:
        session_id = f"{SESSION_ID_PREFIX}{secrets.token_hex(4)}"
        session = {
            "session_id": session_id,
            "thread_id": session_id,
            "company": COMPANY_SLUG,
            "agent_id": AGENT_ID,
            "status": "idle",
            "messages": [],
            "draft": "",
            "order": None,
            "created_at": _utcnow(),
        }
        self._sessions[session_id] = session
        return self.public_session(session_id)

    def get(self, session_id: str) -> dict[str, Any] | None:
        if session_id not in self._sessions:
            return None
        return self.public_session(session_id)

    def require(self, session_id: str) -> dict[str, Any]:
        if session_id not in self._sessions:
            raise KeyError(session_id)
        return self._sessions[session_id]

    def append_message(self, session_id: str, role: str, content: str, status: str | None = None) -> None:
        row: dict[str, Any] = {"role": role, "content": content, "created_at": _utcnow()}
        if status:
            row["status"] = status
        self._sessions[session_id]["messages"].append(row)

    def set_draft(self, session_id: str, content: str) -> None:
        self._sessions[session_id]["draft"] = content

    def set_status(self, session_id: str, status: str) -> None:
        self._sessions[session_id]["status"] = status

    def remember_placed(self, session_id: str) -> dict[str, Any] | None:
        order = self._sessions[session_id].get("order")
        if not isinstance(order, dict) or order.get("status") != "placed" or order.get("recorded"):
            return None
        order["recorded"] = True
        record = {
            "session_id": session_id,
            "placed_at": _utcnow(),
            **deepcopy(order),
        }
        self._placed.append(record)
        return record

    def placed_orders(self) -> list[dict[str, Any]]:
        return deepcopy(self._placed)

    def public_session(self, session_id: str) -> dict[str, Any]:
        session = self._sessions[session_id]
        return {
            "event": EVENT_SESSION,
            "session_id": session["session_id"],
            "thread_id": session["thread_id"],
            "company": session["company"],
            "agent_id": session["agent_id"],
            "status": session["status"],
            "messages": deepcopy(session["messages"]),
            "draft": session.get("draft") or "",
            "order": deepcopy(session.get("order")),
            "created_at": session["created_at"],
        }


class ConciergeHub:
    """One publish reaches every WebSocket on the session and every SSE subscriber."""

    def __init__(self) -> None:
        self._ws: dict[str, list[asyncio.Queue]] = {}
        self._sse: dict[str, list[asyncio.Queue]] = {}
        self._history: dict[str, list[StreamEvent]] = {}
        self._seq: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def reset(self) -> None:
        self._ws.clear()
        self._sse.clear()
        self._history.clear()
        self._seq.clear()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe_ws(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._ws.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe_ws(self, session_id: str, queue: asyncio.Queue) -> None:
        listeners = self._ws.get(session_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners:
            self._ws.pop(session_id, None)

    def subscribe_sse(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._sse.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe_sse(self, session_id: str, queue: asyncio.Queue) -> None:
        listeners = self._sse.get(session_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners:
            self._sse.pop(session_id, None)

    def since(self, session_id: str, last_event_id: str | None) -> list[StreamEvent]:
        history = self._history.get(session_id, [])
        if not last_event_id:
            return []
        try:
            cursor = int(last_event_id)
        except ValueError:
            return list(history)
        return [item for item in history if int(item.id) > cursor]

    async def publish(self, session_id: str, payload: dict[str, Any]) -> StreamEvent:
        self._seq[session_id] = self._seq.get(session_id, 0) + 1
        event_name = str(payload.get("event") or "message")
        item = StreamEvent(str(self._seq[session_id]), event_name, payload)
        history = self._history.setdefault(session_id, [])
        history.append(item)
        if len(history) > HISTORY_LIMIT:
            self._history[session_id] = history[-HISTORY_LIMIT:]
        for queue in list(self._ws.get(session_id, [])):
            await queue.put(payload)
        for queue in list(self._sse.get(session_id, [])):
            await queue.put(item)
        return item


def error_event(detail: str) -> dict[str, str]:
    return {"event": EVENT_ERROR, "detail": detail}


def token_event(session_id: str, delta: str) -> dict[str, str]:
    return {
        "event": EVENT_TOKEN,
        "session_id": session_id,
        "thread_id": session_id,
        "delta": delta,
    }


def assistant_event(session_id: str, content: str, status: str, new_input: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": EVENT_COMPLETED if status == "complete" else EVENT_INTERRUPTED,
        "session_id": session_id,
        "thread_id": session_id,
        "content": content,
        "status": status,
    }
    if status == "interrupted" and new_input:
        payload["new_input"] = new_input
    return payload


class ConciergeProducer:
    def __init__(self, session_id: str, sessions: ConciergeStore, events: ConciergeHub) -> None:
        self.session_id = session_id
        self._sessions = sessions
        self._events = events
        self._task: asyncio.Task | None = None
        self._cancel = asyncio.Event()
        self._new_input = ""

    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start_turn(self, content: str) -> None:
        text = (content or "").strip()
        if not text:
            await self._events.publish(self.session_id, error_event("content is required"))
            return
        if self.busy():
            await self.interrupt(text)
            return
        self._cancel = asyncio.Event()
        self._task = asyncio.create_task(self._turn(text))

    async def wait(self) -> None:
        task = self._task
        if task is not None:
            await task

    async def interrupt(self, new_input: str = "") -> None:
        follow = (new_input or "").strip()
        self._new_input = follow
        self._cancel.set()
        task = self._task
        if task and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._new_input = ""
        if follow:
            await self.start_turn(follow)

    async def _turn(self, content: str) -> None:
        session_id = self.session_id
        session = self._sessions.require(session_id)
        self._sessions.append_message(session_id, "user", content)
        self._sessions.set_draft(session_id, "")
        self._sessions.set_status(session_id, "streaming")
        await self._events.publish(session_id, self._sessions.public_session(session_id))
        answer = reply(session, content)
        pieces: list[str] = []
        finished = True
        try:
            for delta in stream_chunks(answer):
                if self._cancel.is_set():
                    finished = False
                    break
                pieces.append(delta)
                self._sessions.set_draft(session_id, "".join(pieces))
                await self._events.publish(session_id, token_event(session_id, delta))
                delay = float(os.getenv("BRASALAND_CONCIERGE_TOKEN_DELAY", "0") or "0")
                if delay:
                    await asyncio.sleep(delay)
        except asyncio.CancelledError:
            finished = False
            raise
        spoken = "".join(pieces)
        status = "complete" if finished and not self._cancel.is_set() else "interrupted"
        if spoken or status == "interrupted":
            self._sessions.append_message(session_id, "assistant", spoken, status=status)
        self._sessions.set_draft(session_id, "")
        self._sessions.set_status(session_id, "idle" if status == "complete" else "interrupted")
        await self._events.publish(
            session_id,
            assistant_event(session_id, spoken, status, new_input=self._new_input),
        )
        if status == "complete":
            placed = self._sessions.remember_placed(session_id)
            if placed is not None:
                await self._events.publish(
                    session_id,
                    {"event": EVENT_ORDER, "session_id": session_id, "order": placed},
                )
        await self._events.publish(session_id, self._sessions.public_session(session_id))


class ProducerRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ConciergeProducer] = {}

    def reset(self) -> None:
        self._items.clear()

    def get(self, session_id: str, sessions: ConciergeStore, events: ConciergeHub) -> ConciergeProducer:
        producer = self._items.get(session_id)
        if producer is None:
            producer = ConciergeProducer(session_id, sessions, events)
            self._items[session_id] = producer
        return producer


store = ConciergeStore()
hub = ConciergeHub()
producers = ProducerRegistry()


def reset_concierge_state() -> None:
    store.reset()
    hub.reset()
    producers.reset()
