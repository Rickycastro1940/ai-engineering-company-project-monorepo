"""RFP registration on the central API, with a JWT SSE stream of new tickets.

``POST /rfp/tickets`` is the registration step: the file is stored, the ticket
is saved with status ``analyzing``, and subscribers on ``GET /notifications/stream``
receive ``rfp_ticket_created``. Clients cannot choose the status.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from users import get_current_user

from rfp_notifications import (
    KEEPALIVE_SECONDS,
    encode_ticket_event,
    get_ticket,
    hub,
    list_tickets,
    register_rfp,
    sse_payload,
    tickets_after,
)

router = APIRouter(tags=["rfp"])


def _as_http(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.get("/rfp/tickets")
def list_rfp_tickets(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    limit: int = 50,
) -> dict[str, Any]:
    """Snapshot used on dashboard load and after a reconnect."""
    rows = list_tickets(limit=limit)
    public = [sse_payload(row) for row in rows]
    return {"tickets": public, "count": len(public)}


@router.get("/rfp/tickets/{ticket_id}")
def read_rfp_ticket(
    ticket_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return sse_payload(ticket)


@router.post("/rfp/tickets", status_code=201)
async def create_rfp_ticket(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    file: UploadFile = File(...),
    client_name: str = Form(...),
    location: str = Form(...),
    locations: str = Form(...),
    service_type: str = Form(...),
    scope: str = Form(...),
    deadline: str = Form(...),
    budget_range: str | None = Form(default=None),
    departments_needed: str = Form(default=""),
    title: str | None = Form(default=None),
) -> dict[str, Any]:
    """Register one Brasaland RFP. Status is always ``analyzing``."""
    raw = await file.read()
    try:
        ticket = register_rfp(
            client_name=client_name,
            location=location,
            locations=[locations],
            service_type=service_type,
            scope=scope,
            deadline=deadline,
            budget_range=budget_range,
            departments_needed=[departments_needed] if departments_needed else [],
            original_filename=file.filename or "rfp.pdf",
            file_bytes=raw,
            title=title,
        )
    except ValueError as error:
        raise _as_http(error) from error
    finally:
        await file.close()
    hub.publish(ticket)
    return sse_payload(ticket)


async def iter_rfp_notifications(last_event_id: str | None):
    """SSE frames: keep-alive, replay, then live ``rfp_ticket_created`` events."""
    hub.bind_loop(asyncio.get_running_loop())
    queue = hub.subscribe()
    sent: set[int] = set()
    try:
        yield ": keep-alive\n\n"
        for ticket in tickets_after(last_event_id):
            sent.add(int(ticket["event_id"]))
            yield encode_ticket_event(ticket)
        while True:
            try:
                ticket = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            event_id = int(ticket["event_id"])
            if event_id in sent:
                continue
            sent.add(event_id)
            yield encode_ticket_event(ticket)
    finally:
        hub.unsubscribe(queue)


@router.get("/notifications/stream")
async def stream_rfp_notifications(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Push ``rfp_ticket_created`` as ``text/event-stream``."""
    return StreamingResponse(
        iter_rfp_notifications(last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
