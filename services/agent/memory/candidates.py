"""Build memory write candidates only for CONTEXT-company.md memorable domains."""

from __future__ import annotations

from typing import Any

from data.pipelines.rag import NO_CONTEXT_ANSWER

from services.agent.memory.policy import evaluate_memory_candidate, sanitize_record_dict
from services.agent.state import AgentState


def _candidate(
    text: str,
    *,
    kind: str | None,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "text": text.strip(),
        "kind": kind,
        "source": source,
        "metadata": sanitize_record_dict(metadata or {}),
    }


def extract_memory_candidates(state: AgentState) -> list[dict[str, Any]]:
    """Propose facts from grounded RAG answers that fall under CONTEXT domains.

    Ticket/inventory tool payloads are **not** listed as memorable topics in
    ``CONTEXT-company.md`` (those stay in traces / live MCP calls). Memorable
    domains are the four KB topic areas + key people only.
    """
    candidates: list[dict[str, Any]] = []
    answer = (state.get("answer") or "").strip()

    # CONTEXT: unknown answers must use the fixed phrase — never learn it as a fact.
    if not answer or answer == NO_CONTEXT_ANSWER:
        return []

    retrieved = state.get("retrieved") or []
    if not retrieved:
        # Without KB grounding we do not invent memorable facts from free text.
        return []

    # Never persist chunk bodies / scores — only the model answer string + source names.
    sources = sorted(
        {
            str(c.get("source_document") or "").strip()
            for c in retrieved
            if isinstance(c, dict) and c.get("source_document")
        }
    )
    # Drop any accidental score-bearing metadata (CONTEXT: never scores/payloads).
    safe_meta = sanitize_record_dict(
        {"kb_sources": sources, "question": state.get("question")}
    )
    candidates.append(
        _candidate(
            answer,
            kind=None,  # inferred strictly via CONTEXT domain hints
            source="rag_answer",
            metadata=safe_meta,
        )
    )

    admitted: list[dict[str, Any]] = []
    for item in candidates:
        decision = evaluate_memory_candidate(
            item["text"],
            kind=item.get("kind"),
            source=item.get("source"),
        )
        if decision.allowed:
            admitted.append({**item, "kind": decision.kind})
    return admitted
