"""Classify whether a support question needs the RAG, ticket tool, or both."""

from __future__ import annotations

import re
from typing import Any

from services.agent.tools.contracts import TicketLookupInput

# Brasaland incident ids look like BRS-000001
TICKET_ID_RE = re.compile(r"\bBRS-\d{6}\b", re.IGNORECASE)

_TICKET_HINTS = (
    "ticket",
    "incident",
    "incidencia",
    "incidente",
    "estado del",
    "status of",
    "support ticket",
    "case #",
    "case number",
)

_RAG_HINTS = (
    "policy",
    "policies",
    "procedure",
    "procedimiento",
    "política",
    "politica",
    "how do",
    "how should",
    "how to",
    "minimum stock",
    "supplier",
    "proveedor",
    "approval",
    "lucía",
    "lucia",
    "procurement",
    "knowledge",
    "handbook",
    "guideline",
    "what is the",
    "what are the",
)


def extract_ticket_id(question: str) -> str | None:
    match = TICKET_ID_RE.search(question or "")
    return match.group(0).upper() if match else None


def classify_sources(question: str) -> dict[str, Any]:
    """Decide RAG vs ticket tool from question content (no user hint required).

    Returns
    -------
    dict with keys:
      needs_ticket, needs_rag, ticket_query (dict|None), route
      (``ticket`` | ``retrieve`` | ``both``)
    """
    text = (question or "").strip()
    lowered = text.casefold()
    ticket_id = extract_ticket_id(text)
    mentions_ticket = bool(ticket_id) or any(h in lowered for h in _TICKET_HINTS)
    mentions_rag = any(h in lowered for h in _RAG_HINTS)

    needs_ticket = mentions_ticket
    if needs_ticket and not mentions_rag:
        # Pure operational lookup — skip RAG.
        needs_rag = False
    elif mentions_rag and not needs_ticket:
        needs_rag = True
    elif needs_ticket and mentions_rag:
        needs_rag = True
    else:
        # Default: documentation / procedure questions go to RAG.
        needs_rag = True
        needs_ticket = False

    ticket_query: dict[str, Any] | None = None
    if needs_ticket:
        if ticket_id:
            ticket_query = TicketLookupInput(ticket_id=ticket_id).model_dump()
        else:
            # Keyword-only ticket question without an id → open-status scan as a
            # safe, read-only default (still hits the real incident API).
            ticket_query = TicketLookupInput(status="ABIERTO").model_dump()

    if needs_ticket and needs_rag:
        route = "both"
    elif needs_ticket:
        route = "ticket"
    else:
        route = "retrieve"

    return {
        "needs_ticket": needs_ticket,
        "needs_rag": needs_rag,
        "ticket_query": ticket_query,
        "route": route,
    }
