"""Thin HTTP routes for Brasaland RFP intake — logic in data/pipelines/rfp_intake."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from data.pipelines.rfp_intake import IntakeResult, run_intake_from_bytes
from data.pipelines.rfp_intake.constants import P1_TERMINAL, STATUS_ANALYZING, STATUS_FAILED
from services.rfp.store import (
    create_analyzing_ticket,
    get_ticket,
    list_tickets,
    save_intake_result,
    ticket_to_dict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "rfp"

router = APIRouter(prefix="/rfp", tags=["rfp-intake"])


def _safe_filename(filename: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", Path(filename).name)[:180] or "rfp.pdf"


def _persist_upload(ticket_id: str, raw: bytes, filename: str) -> Path:
    """Store upload under data/raw/rfp/<ticket_id>/ (runtime artifact)."""
    store = RAW_DIR / ticket_id
    store.mkdir(parents=True, exist_ok=True)
    path = store / _safe_filename(filename)
    path.write_bytes(raw)
    return path


def _run_pipeline_job(ticket_id: str, raw: bytes, filename: str, title: str | None) -> None:
    store = RAW_DIR / ticket_id
    try:
        result, pdf_path = run_intake_from_bytes(
            raw=raw, filename=filename, title=title, store_dir=store
        )
        try:
            rel = str(pdf_path.relative_to(REPO_ROOT))
        except ValueError:
            rel = str(pdf_path)
        save_intake_result(ticket_id, result, source_pdf_path=rel)
    except Exception as exc:  # noqa: BLE001
        failed = IntakeResult(
            status=STATUS_FAILED,
            metadata={},
            departments_needed=[],
            sections={},
            unmapped_topics=[],
            conflicts=[],
            intake_summary="",
            requires_ceo_approval=False,
            markdown_text="",
            readability_scores={},
            error_message=f"{type(exc).__name__}: {exc}",
        )
        pdf_path = store / _safe_filename(filename)
        try:
            rel = str(pdf_path.relative_to(REPO_ROOT)) if pdf_path.is_file() else ""
        except ValueError:
            rel = str(pdf_path) if pdf_path.is_file() else ""
        save_intake_result(ticket_id, failed, source_pdf_path=rel)


def _sync_mode() -> bool:
    return (os.getenv("RFP_INTAKE_SYNC") or "").strip().lower() in {"1", "true", "yes"}


@router.post("/tickets")
async def create_ticket(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
) -> dict[str, Any]:
    """Ticket-mode upload: returns quickly with status=analyzing; pipeline runs async."""
    original = file.filename or "rfp.pdf"
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")

    ticket = create_analyzing_ticket(title=(title or "").strip() or None)
    # Persist PDF under data/raw/ before returning so analyzing tickets have artifacts.
    _persist_upload(ticket.ticket_id, raw, original)

    if _sync_mode():
        _run_pipeline_job(ticket.ticket_id, raw, original, title)
        saved = get_ticket(ticket.ticket_id)
        assert saved is not None
        payload = ticket_to_dict(saved)
        payload["terminal"] = saved.status in P1_TERMINAL
        return payload

    background_tasks.add_task(_run_pipeline_job, ticket.ticket_id, raw, original, title)
    return {
        "ticket_id": ticket.ticket_id,
        "status": STATUS_ANALYZING,
        "created_at": ticket.created_at,
        "terminal": False,
    }


@router.post("/upload")
async def upload_compat(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
) -> dict[str, Any]:
    """Backoffice alias for POST /rfp/tickets."""
    return await create_ticket(background_tasks, file=file, title=title)


@router.get("/tickets")
def list_rfp_tickets(limit: int = 50) -> dict[str, Any]:
    rows = [ticket_to_dict(t) for t in list_tickets(limit=limit)]
    return {"tickets": rows, "count": len(rows)}


@router.get("/part2/queue")
def part2_queue(limit: int = 50) -> dict[str, Any]:
    """DB-backed Part 2 queue (same API process — not a second service)."""
    from services.rfp.store import list_part2_queue

    items = list_part2_queue(limit=limit)
    return {"queue": items, "count": len(items)}


@router.get("/tickets/{ticket_id}/part2-handoff")
def get_part2_handoff(ticket_id: str) -> dict[str, Any]:
    """Return ticket_id + synthesizer work_streams for Part 2 (no PDF reparse)."""
    from services.rfp.store import load_part2_handoff

    try:
        return load_part2_handoff(ticket_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ticket not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tickets/{ticket_id}")
def get_rfp_ticket(ticket_id: str) -> dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    payload = ticket_to_dict(ticket)
    payload["terminal"] = ticket.status in P1_TERMINAL
    return payload
