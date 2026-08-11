"""Build memory write candidates from LangGraph state (post-answer)."""

from __future__ import annotations

from typing import Any

from data.pipelines.rag import NO_CONTEXT_ANSWER

from services.agent.memory.policy import evaluate_memory_candidate, sanitize_record_dict
from services.agent.state import AgentState


def _candidate(text: str, *, kind: str | None, source: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "text": text.strip(),
        "kind": kind,
        "source": source,
        "metadata": sanitize_record_dict(metadata or {}),
    }


def extract_memory_candidates(state: AgentState) -> list[dict[str, Any]]:
    """Propose semantic facts from successful tool/RAG outcomes only."""
    candidates: list[dict[str, Any]] = []
    answer = (state.get("answer") or "").strip()

    # Never learn the unknown placeholder.
    if answer and answer != NO_CONTEXT_ANSWER:
        # Prefer structured tool outcomes over free-form answer text when present.
        pass

    ticket = state.get("ticket_result") or {}
    if ticket.get("ok") and ticket.get("tickets"):
        for ticket_row in ticket["tickets"]:
            if not isinstance(ticket_row, dict):
                continue
            incident_id = str(ticket_row.get("incident_id") or "").strip()
            status = str(ticket_row.get("status") or "").strip()
            category = str(ticket_row.get("category") or "").strip()
            if incident_id and status:
                text = (
                    f"Ticket {incident_id}: status={status}"
                    + (f", category={category}" if category else "")
                    + " (confirmed via Incidents Manager / MCP)."
                )
                candidates.append(
                    _candidate(
                        text,
                        kind="ticket",
                        source="mcp_incidents",
                        metadata={
                            "incident_id": incident_id,
                            "status": status,
                            "category": category or None,
                        },
                    )
                )

    inventory = state.get("inventory_result") or {}
    if inventory.get("ok") and inventory.get("products"):
        for product in inventory["products"][:5]:
            if not isinstance(product, dict):
                continue
            name = str(product.get("name") or "").strip()
            product_id = str(product.get("product_id") or "").strip()
            quantity = product.get("quantity")
            unit = str(product.get("unit") or "").strip()
            if name and quantity is not None:
                text = (
                    f"Inventory {name} (product_id={product_id}): "
                    f"quantity={quantity}{(' ' + unit) if unit else ''} "
                    "(confirmed via inventory manager)."
                )
                candidates.append(
                    _candidate(
                        text,
                        kind="inventory",
                        source="inventory_tool",
                        metadata={
                            "product_id": product_id,
                            "name": name,
                            "quantity": quantity,
                            "unit": unit or None,
                        },
                    )
                )

    # Grounded RAG answers (no chunk payloads) — store the answer as a semantic note
    # only when retrieve produced context and answer is not the unknown placeholder.
    retrieved = state.get("retrieved") or []
    if retrieved and answer and answer != NO_CONTEXT_ANSWER:
        sources = sorted(
            {
                str(c.get("source_document") or "").strip()
                for c in retrieved
                if isinstance(c, dict) and c.get("source_document")
            }
        )
        # One compact memory line — never persist chunk text / scores.
        text = f"Brasaland ops fact (from KB): {answer}"
        candidates.append(
            _candidate(
                text,
                kind=None,  # inferred by policy from answer content
                source="rag_answer",
                metadata={"kb_sources": sources, "question": state.get("question")},
            )
        )

    # Filter through policy up-front so callers see only admissible candidates.
    admitted: list[dict[str, Any]] = []
    for item in candidates:
        decision = evaluate_memory_candidate(
            item["text"],
            kind=item.get("kind"),
            source=item.get("source"),
        )
        if decision.allowed:
            item = {**item, "kind": decision.kind}
            admitted.append(item)
    return admitted
