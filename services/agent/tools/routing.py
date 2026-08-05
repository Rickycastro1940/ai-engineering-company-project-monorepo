"""Classify whether a support question needs RAG, ticket tool, inventory, or a mix."""

from __future__ import annotations

import re
from typing import Any

from services.agent.tools.contracts import InventoryLookupInput, TicketLookupInput

# Brasaland incident ids look like BRS-000001
TICKET_ID_RE = re.compile(r"\bBRS-\d{6}\b", re.IGNORECASE)
PRODUCT_ID_RE = re.compile(r"\bproduct(?:\s+id)?\s*[#:]?\s*(\d+)\b", re.IGNORECASE)

_TICKET_HINTS = (
    "ticket",
    "incident",
    "incidencia",
    "incidente",
    "estado del",
    "status of ticket",
    "status of incident",
    "support ticket",
    "case #",
    "case number",
)

# Operational stock questions (live inventory) — not policy/RAG.
_INVENTORY_HINTS = (
    "inventory",
    "in stock",
    "stock of",
    "do we have",
    "have we got",
    "how many",
    "quantity of",
    "on hand",
    "warehouse stock",
    "product stock",
)

# Known product names from products.csv (live inventory manager seed).
_KNOWN_PRODUCT_NAMES = (
    "tomatoes",
    "tomato",
    "mozzarella",
    "napkins",
    "napkin",
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
    "stock rule",
    "supplier",
    "proveedor",
    "approval",
    "lucía",
    "lucia",
    "fernández",
    "fernandez",
    "procurement",
    "knowledge",
    "handbook",
    "guideline",
    "protein",
    "emergency order",
)


def extract_ticket_id(question: str) -> str | None:
    match = TICKET_ID_RE.search(question or "")
    return match.group(0).upper() if match else None


def extract_product_id(question: str) -> str | None:
    match = PRODUCT_ID_RE.search(question or "")
    return match.group(1) if match else None


def extract_product_name(question: str) -> str | None:
    lowered = (question or "").casefold()
    for name in _KNOWN_PRODUCT_NAMES:
        if name in lowered:
            # Prefer plural/canonical CSV names.
            if name.startswith("tomato"):
                return "Tomatoes"
            if name.startswith("napkin"):
                return "Napkins"
            if name == "mozzarella":
                return "Mozzarella"
            return name.title()
    return None


def classify_sources(question: str) -> dict[str, Any]:
    """Decide RAG vs ticket tool vs inventory tool from question content.

    Returns
    -------
    dict with keys:
      needs_ticket, needs_inventory, needs_rag,
      ticket_query, inventory_query, route
      (``ticket`` | ``inventory`` | ``retrieve`` | ``both`` |
       ``inventory_rag`` | ``ticket_inventory`` | ``all``)
    """
    text = (question or "").strip()
    lowered = text.casefold()
    ticket_id = extract_ticket_id(text)
    product_id = extract_product_id(text)
    product_name = extract_product_name(text)

    mentions_ticket = bool(ticket_id) or any(h in lowered for h in _TICKET_HINTS)
    # "status of" alone is too broad; require ticket hints or BRS id (already covered).
    if "status of" in lowered and not mentions_ticket and ("ticket" in lowered or "incident" in lowered or "incidencia" in lowered):
        mentions_ticket = True

    mentions_inventory = (
        bool(product_id)
        or bool(product_name)
        or any(h in lowered for h in _INVENTORY_HINTS)
    )
    # Policy "stock rule" / "minimum stock" is RAG, not live inventory.
    if any(h in lowered for h in ("minimum stock", "stock rule", "emergency order")):
        mentions_inventory = False

    mentions_rag = any(h in lowered for h in _RAG_HINTS)

    needs_ticket = mentions_ticket
    needs_inventory = mentions_inventory
    if needs_ticket or needs_inventory:
        needs_rag = bool(mentions_rag)
        # Pure operational lookups skip RAG.
        if (needs_ticket or needs_inventory) and not mentions_rag:
            needs_rag = False
    else:
        needs_rag = True

    ticket_query: dict[str, Any] | None = None
    if needs_ticket:
        if ticket_id:
            ticket_query = TicketLookupInput(ticket_id=ticket_id).model_dump()
        else:
            ticket_query = TicketLookupInput(status="ABIERTO").model_dump()

    inventory_query: dict[str, Any] | None = None
    if needs_inventory:
        inventory_query = InventoryLookupInput(
            product_id=product_id,
            name_contains=product_name,
        ).model_dump()

    if needs_ticket and needs_inventory and needs_rag:
        route = "all"
    elif needs_ticket and needs_inventory:
        route = "ticket_inventory"
    elif needs_ticket and needs_rag:
        route = "both"
    elif needs_inventory and needs_rag:
        route = "inventory_rag"
    elif needs_ticket:
        route = "ticket"
    elif needs_inventory:
        route = "inventory"
    else:
        route = "retrieve"

    return {
        "needs_ticket": needs_ticket,
        "needs_inventory": needs_inventory,
        "needs_rag": needs_rag,
        "ticket_query": ticket_query,
        "inventory_query": inventory_query,
        "route": route,
    }
