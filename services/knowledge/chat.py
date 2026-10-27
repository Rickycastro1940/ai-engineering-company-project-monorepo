"""In-memory chat sessions for the Brasaland knowledge assistant.

The assistant produces named events onto ``ChatEventHub``. WebSocket
connections subscribe and forward those events. Generation does not call
``websocket.send_json``.
"""

from __future__ import annotations

import asyncio
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from data.pipelines.rag import query_stream

COMPANY_SLUG = "brasaland"
AGENT_ID = "brasaland_knowledge_assistant"
SESSION_ID_PREFIX = "BRS-CHAT-"
EVENT_USER_MESSAGE = "knowledge_user_message"
EVENT_INTERRUPT = "knowledge_interrupt"
EVENT_AUTH = "knowledge_auth"
EVENT_SESSION = "knowledge_session"
EVENT_TOKEN = "knowledge_token"
EVENT_ASSISTANT_MESSAGE = "knowledge_assistant_message"
EVENT_ERROR = "knowledge_error"
# Token UI matches LangGraph stream_mode="messages". This agent is not a graph.
STREAM_MODE = "messages"
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_NO_THREAD = 4404
WS_CLOSE_BUSY = 4409
AUTH_TIMEOUT_SECONDS = 5.0
PART1_EVENT_NAMES = frozenset(
    {
        "emergency_order_created",
        "waste_escalation_created",
        "rfp_ticket_created",
        "message",
    }
)


class SessionBusyError(Exception):
    """Another socket is already attached to this conversation."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ChatSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._attached: set[str] = set()
        self._seq = 0

    def reset(self) -> None:
        self._sessions.clear()
        self._attached.clear()
        self._seq = 0

    def create(self) -> dict[str, Any]:
        self._seq += 1
        session_id = f"{SESSION_ID_PREFIX}{self._seq:06d}"
        session = {
            "session_id": session_id,
            "thread_id": session_id,
            "company": COMPANY_SLUG,
            "agent_id": AGENT_ID,
            "status": "idle",
            "messages": [],
            "created_at": _utcnow(),
        }
        self._sessions[session_id] = session
        return deepcopy(session)

    def get(self, session_id: str) -> dict[str, Any] | None:
        session = self._sessions.get(session_id)
        return deepcopy(session) if session else None

    def attach(self, session_id: str) -> dict[str, Any]:
        if session_id not in self._sessions:
            raise KeyError(session_id)
        if session_id in self._attached:
            raise SessionBusyError(session_id)
        self._attached.add(session_id)
        return self.public_session(session_id)

    def detach(self, session_id: str) -> None:
        self._attached.discard(session_id)

    def set_status(self, session_id: str, status: str) -> None:
        self._sessions[session_id]["status"] = status

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self._sessions[session_id]["messages"].append(
            {"role": role, "content": content, "created_at": _utcnow()}
        )

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
            "created_at": session["created_at"],
        }


class ChatEventHub:
    """In-process pub/sub keyed by session id. Redis is not required."""

    def __init__(self) -> None:
        self._topics: dict[str, list[asyncio.Queue]] = {}

    def reset(self) -> None:
        self._topics.clear()

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._topics.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        listeners = self._topics.get(session_id, [])
        if queue in listeners:
            listeners.remove(queue)
        if not listeners:
            self._topics.pop(session_id, None)

    async def publish(self, session_id: str, payload: dict[str, Any]) -> None:
        for queue in list(self._topics.get(session_id, [])):
            await queue.put(payload)


def knowledge_error_event(detail: str) -> dict[str, str]:
    return {"event": EVENT_ERROR, "detail": detail}


def token_event(session_id: str, delta: str) -> dict[str, str]:
    return {
        "event": EVENT_TOKEN,
        "session_id": session_id,
        "thread_id": session_id,
        "delta": delta,
    }


def assistant_event(session_id: str, content: str, status: str) -> dict[str, str]:
    return {
        "event": EVENT_ASSISTANT_MESSAGE,
        "session_id": session_id,
        "thread_id": session_id,
        "content": content,
        "status": status,
    }


class KnowledgeProducer:
    """Runs one turn and publishes tokens. Does not touch the socket."""

    def __init__(self, session_id: str, sessions: ChatSessionStore, events: ChatEventHub) -> None:
        self.session_id = session_id
        self._sessions = sessions
        self._events = events
        self._task: asyncio.Task | None = None
        self._cancel = asyncio.Event()

    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start_turn(self, content: str) -> None:
        text = (content or "").strip()
        if not text:
            await self._events.publish(
                self.session_id,
                knowledge_error_event("content is required"),
            )
            return
        if self.busy():
            await self._events.publish(
                self.session_id,
                knowledge_error_event("a reply is already streaming"),
            )
            return
        self._cancel = asyncio.Event()
        self._task = asyncio.create_task(self._turn(text))

    async def interrupt(self, content: str = "") -> None:
        self._cancel.set()
        task = self._task
        if task and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
        follow = (content or "").strip()
        if follow:
            await self.start_turn(follow)

    async def abort_generation(self) -> None:
        self._cancel.set()
        task = self._task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _turn(self, content: str) -> None:
        session_id = self.session_id
        self._sessions.append_message(session_id, "user", content)
        self._sessions.set_status(session_id, "streaming")
        await self._events.publish(session_id, self._sessions.public_session(session_id))
        pieces: list[str] = []
        finished = False
        generator = query_stream(content)
        try:
            while not self._cancel.is_set():
                delta = await asyncio.to_thread(_next_delta, generator)
                if delta is None:
                    finished = True
                    break
                pieces.append(delta)
                await self._events.publish(session_id, token_event(session_id, delta))
                delay = float(os.getenv("BRASALAND_CHAT_TOKEN_DELAY", "0") or "0")
                await asyncio.sleep(delay)
        finally:
            generator.close()
        answer = "".join(pieces)
        status = "complete" if finished and not self._cancel.is_set() else "interrupted"
        if answer or status == "interrupted":
            self._sessions.append_message(session_id, "assistant", answer)
        self._sessions.set_status(session_id, "idle" if status == "complete" else "interrupted")
        await self._events.publish(session_id, assistant_event(session_id, answer, status))
        await self._events.publish(session_id, self._sessions.public_session(session_id))


def _next_delta(generator) -> str | None:
    try:
        return next(generator)
    except StopIteration:
        return None


class ProducerRegistry:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeProducer] = {}

    def reset(self) -> None:
        self._items.clear()

    def get(self, session_id: str, sessions: ChatSessionStore, events: ChatEventHub) -> KnowledgeProducer:
        producer = self._items.get(session_id)
        if producer is None:
            producer = KnowledgeProducer(session_id, sessions, events)
            self._items[session_id] = producer
        return producer

    def drop(self, session_id: str) -> None:
        self._items.pop(session_id, None)


store = ChatSessionStore()
hub = ChatEventHub()
producers = ProducerRegistry()


def reset_chat_state() -> None:
    store.reset()
    hub.reset()
    producers.reset()
