"""Guest concierge routes on the central API.

WebSocket ``/concierge/ws`` uses the same token events as ``/knowledge/ws``.
SSE ``GET /realtime/concierge/stream`` uses the same frame shape as
``GET /realtime/ops-alerts/stream`` (id, event, data, Last-Event-ID, keep-alive).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from users import get_current_user

from services.concierge.session import (
    EVENT_SNAPSHOT,
    hub,
    producers,
    store,
)
from services.concierge.socket import run_concierge_websocket
from services.concierge.transcribe import AudioModelError, resolve_transcript

logger = logging.getLogger("brasaland.concierge")

router = APIRouter(prefix="/concierge", tags=["concierge"])
realtime = APIRouter(prefix="/realtime", tags=["concierge"])
UI_PAGE = Path(__file__).resolve().parents[2] / "uis" / "concierge" / "index.html"


class MessageBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


def _missing_session() -> HTTPException:
    return HTTPException(status_code=404, detail="Concierge session was not found.")


@router.post("/sessions", status_code=201)
def create_concierge_session() -> dict[str, Any]:
    """Open a guest thread. The menu is public, so this does not require a staff JWT."""
    return store.create()


@router.get("/sessions/{session_id}")
def read_concierge_session(session_id: str) -> dict[str, Any]:
    session = store.get(session_id)
    if session is None:
        raise _missing_session()
    return session


@router.post("/sessions/{session_id}/messages")
async def post_concierge_message(session_id: str, body: MessageBody) -> dict[str, Any]:
    """Run one turn to completion. Tokens are also published for SSE and WebSocket listeners."""
    try:
        store.require(session_id)
    except KeyError as error:
        raise _missing_session() from error
    producer = producers.get(session_id, store, hub)
    await producer.start_turn(body.content)
    await producer.wait()
    session = store.get(session_id)
    if session is None:
        raise _missing_session()
    answer = ""
    for message in reversed(session["messages"]):
        if message["role"] == "assistant":
            answer = message["content"]
            break
    return {"answer": answer, "session": session}


@router.get("/orders")
def list_concierge_orders(_user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
    """Placed guest orders for Restaurant Operations. Drafts stay on the guest session."""
    return {"orders": store.placed_orders()}


@router.post("/transcribe")
async def transcribe_order(request: Request) -> dict[str, Any]:
    """Turn a voice clip into text when ``BRASALAND_AUDIO_API_KEY`` is set.

    With no key, JSON ``{"text": "..."}`` or form field ``text`` is the order.
    Audio bytes without a key do not call a model.
    """
    content_type = request.headers.get("content-type", "")
    text = ""
    audio: bytes | None = None
    filename = ""
    mime = ""
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception as error:
            raise HTTPException(status_code=400, detail="Transcription body must be JSON or form data.") from error
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Transcription body must be a JSON object.")
        text = str(payload.get("text") or "")
    else:
        form = await request.form()
        text = str(form.get("text") or "")
        upload = form.get("audio")
        if upload is not None and hasattr(upload, "read"):
            audio = await upload.read()
            filename = str(getattr(upload, "filename", "") or "")
            mime = str(getattr(upload, "content_type", "") or "")
            if not audio:
                audio = None
    try:
        result = resolve_transcript(text=text, audio=audio, filename=filename, content_type=mime)
    except AudioModelError as error:
        raise HTTPException(status_code=503, detail="The audio model is unavailable.") from error
    if not result["transcript"] and result["mode"] != "text_fallback":
        raise HTTPException(status_code=400, detail=str(result["detail"]))
    if not result["transcript"] and not audio and not text.strip():
        raise HTTPException(status_code=400, detail=str(result["detail"]))
    logger.info("concierge_transcribe mode=%s", result["mode"])
    return result


@router.websocket("/ws")
async def concierge_socket(websocket: WebSocket) -> None:
    await run_concierge_websocket(websocket)


@router.get("/concierge.js", include_in_schema=False)
def concierge_script() -> FileResponse:
    script = UI_PAGE.with_name("concierge.js")
    if not script.is_file():
        raise HTTPException(status_code=404, detail="Concierge script is not installed")
    return FileResponse(script, media_type="text/javascript")


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def concierge_page() -> FileResponse:
    if not UI_PAGE.is_file():
        raise HTTPException(status_code=404, detail="Concierge page is not installed")
    return FileResponse(UI_PAGE)


def _ping_seconds() -> float:
    import os

    raw = os.getenv("BRASALAND_CONCIERGE_SSE_PING", "15") or "15"
    try:
        return max(float(raw), 0.05)
    except ValueError:
        return 15.0


async def iter_concierge_sse(session_id: str, last_event_id: str | None):
    """SSE frames for one guest thread. Same shape as the no-sales stream."""
    hub.bind_loop(asyncio.get_running_loop())
    queue = hub.subscribe_sse(session_id)
    sent: set[str] = set()
    try:
        yield ": keep-alive\n\n"
        if last_event_id:
            for item in hub.since(session_id, last_event_id):
                sent.add(item.id)
                yield item.encode()
        else:
            snapshot = store.public_session(session_id)
            snapshot["event"] = EVENT_SNAPSHOT
            yield f"event: {EVENT_SNAPSHOT}\ndata: {json.dumps(snapshot, separators=(',', ':'))}\n\n"
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=_ping_seconds())
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if item.id in sent:
                continue
            sent.add(item.id)
            yield item.encode()
    finally:
        hub.unsubscribe_sse(session_id, queue)


@realtime.get("/concierge/stream")
async def stream_concierge(
    session_id: str,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Push ``token_chunk`` and ``generation_completed`` for one guest session."""
    if store.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Concierge session was not found.")
    return StreamingResponse(
        iter_concierge_sse(session_id, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
