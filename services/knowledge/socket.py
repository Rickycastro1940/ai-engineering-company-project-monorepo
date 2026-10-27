"""WebSocket consumer for brasaland_knowledge_assistant.

The handshake URL names an existing thread (``session_id`` or ``thread_id``).
Auth is the same staff JWT as ``POST /auth/login``. The socket only forwards
events published on ``ChatEventHub``.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

from services.knowledge.chat import (
    AUTH_TIMEOUT_SECONDS,
    EVENT_AUTH,
    EVENT_INTERRUPT,
    EVENT_USER_MESSAGE,
    WS_CLOSE_BUSY,
    WS_CLOSE_NO_THREAD,
    WS_CLOSE_UNAUTHORIZED,
    SessionBusyError,
    hub,
    knowledge_error_event,
    producers,
    store,
)


def _token_from_socket(websocket: WebSocket) -> str:
    params = websocket.query_params
    return (params.get("token") or params.get("access_token") or "").strip()


def _thread_from_socket(websocket: WebSocket) -> str:
    params = websocket.query_params
    return (params.get("session_id") or params.get("thread_id") or "").strip()


def _user_for_token(token: str) -> dict:
    from auth import decode_access_token
    from users import get_user_by_id

    subject = decode_access_token(token)
    try:
        user_id = int(subject)
    except ValueError as error:
        raise HTTPException(status_code=401, detail="Could not validate credentials") from error
    user = get_user_by_id(user_id)
    if user is None or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Inactive or missing user")
    return user


async def _authenticate(websocket: WebSocket) -> None:
    token = _token_from_socket(websocket)
    if token:
        _user_for_token(token)
        return
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
    except (WebSocketDisconnect, TimeoutError, asyncio.TimeoutError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=401, detail="Not authenticated") from error
    if not isinstance(data, dict) or data.get("event") != EVENT_AUTH:
        raise HTTPException(status_code=401, detail="Not authenticated")
    frame_token = str(data.get("token") or data.get("access_token") or "")
    _user_for_token(frame_token)


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


async def run_knowledge_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        await _authenticate(websocket)
    except HTTPException:
        await _close(websocket, WS_CLOSE_UNAUTHORIZED, "Not authenticated")
        return

    session_id = _thread_from_socket(websocket)
    try:
        store.attach(session_id)
    except SessionBusyError:
        await _close(websocket, WS_CLOSE_BUSY, "Session already connected")
        return
    except KeyError:
        await _close(
            websocket,
            WS_CLOSE_NO_THREAD,
            "session_id or thread_id must name an existing conversation",
        )
        return

    queue = hub.subscribe(session_id)
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
                await hub.publish(
                    session_id,
                    knowledge_error_event("frame must be JSON with an event field"),
                )
                continue
            if not isinstance(data, dict):
                await hub.publish(
                    session_id,
                    knowledge_error_event("frame must be JSON with an event field"),
                )
                continue
            event = data.get("event")
            if event == EVENT_USER_MESSAGE:
                await producer.start_turn(str(data.get("content") or ""))
            elif event == EVENT_INTERRUPT:
                await producer.interrupt(str(data.get("content") or ""))
            else:
                await hub.publish(
                    session_id,
                    knowledge_error_event(
                        "event must be knowledge_user_message or knowledge_interrupt"
                    ),
                )
    except WebSocketDisconnect:
        pass
    finally:
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass
        hub.unsubscribe(session_id, queue)
        await producer.abort_generation()
        live = store.get(session_id)
        if live and live["status"] == "streaming":
            store.set_status(session_id, "interrupted")
        store.detach(session_id)
        producers.drop(session_id)
