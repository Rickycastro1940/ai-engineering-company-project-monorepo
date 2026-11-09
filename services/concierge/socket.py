"""WebSocket consumer for the guest concierge.

The frame names match manager support (``token_chunk``, ``interrupt``,
``generation_completed``) so a client can stop a reply on the same socket
that is still sending tokens. This guest socket does not require a staff JWT:
the menu is already public on ``GET /menus``.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket, WebSocketDisconnect

from services.concierge.session import (
    EVENT_INTERRUPT,
    EVENT_USER,
    WS_CLOSE_NO_THREAD,
    error_event,
    hub,
    producers,
    store,
)


def _thread_from_socket(websocket: WebSocket) -> str:
    params = websocket.query_params
    return (params.get("session_id") or params.get("thread_id") or "").strip()


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        return


async def _forward(websocket: WebSocket, queue: asyncio.Queue) -> None:
    try:
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except asyncio.CancelledError:
        raise
    except (WebSocketDisconnect, RuntimeError):
        return


async def run_concierge_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id = _thread_from_socket(websocket)
    try:
        store.require(session_id)
    except KeyError:
        await _close(
            websocket,
            WS_CLOSE_NO_THREAD,
            "session_id or thread_id must name an existing conversation",
        )
        return

    queue = hub.subscribe_ws(session_id)
    producer = producers.get(session_id, store, hub)
    consumer = asyncio.create_task(_forward(websocket, queue))
    await hub.publish(session_id, store.public_session(session_id))

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                await hub.publish(session_id, error_event("frame must be JSON with an event field"))
                continue
            if not isinstance(data, dict):
                await hub.publish(session_id, error_event("frame must be JSON with an event field"))
                continue
            event = data.get("event")
            follow = str(data.get("new_input") or data.get("content") or "")
            if event == EVENT_USER:
                await producer.start_turn(follow)
            elif event in {EVENT_INTERRUPT, "support_interrupt"}:
                await producer.interrupt(follow)
            else:
                await hub.publish(
                    session_id,
                    error_event("event must be concierge_user_message or interrupt"),
                )
    except WebSocketDisconnect:
        pass
    finally:
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass
        hub.unsubscribe_ws(session_id, queue)
