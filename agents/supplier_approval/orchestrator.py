"""Collaborative supplier-approval handoff.

Three roles share one LangGraph state, in order:

1. Supplier Agent parses the application.
2. Compliance Agent checks health and ordering standards in the knowledge base.
3. Operations Agent writes the approval summary for management.

The inventory loop in ``agent.py`` stays a manual Groq client. This handoff
is the LangGraph graph in ``graph.py``. Groq rewrites only the operations
narrative when ``BRASALAND_SUPPLIER_AGENTS=groq``.
"""

from __future__ import annotations

from agents.supplier_approval.graph import supplier_approval_graph

ROLES = ("supplier", "compliance", "operations")
ORCHESTRATION = "langgraph"


def review_supplier_application(payload: dict) -> dict:
    state = supplier_approval_graph.invoke(
        {
            "input": payload or {},
            "trace": [],
            "parsed": None,
            "compliance": None,
            "decision": None,
            "conditions": [],
            "summary": None,
            "llm": "not_used",
        }
    )
    if tuple(state["trace"]) != ROLES:
        raise RuntimeError("supplier approval handoff is out of order")
    parsed = state["parsed"]
    compliance = state["compliance"]
    return {
        "decision": state["decision"],
        "summary": state["summary"],
        "conditions": state["conditions"],
        "currency": parsed.get("currency"),
        "market": parsed.get("market"),
        "roles": list(state["trace"]),
        "orchestration": ORCHESTRATION,
        "llm": state["llm"],
        "parsed": {
            "name": parsed.get("name"),
            "country": parsed.get("country"),
            "market": parsed.get("market"),
            "currency": parsed.get("currency"),
            "categories": parsed.get("categories"),
            "emergency_surcharge_pct": parsed.get("emergency_surcharge_pct"),
            "status": parsed.get("status"),
            "complete": parsed.get("complete"),
            "gaps": parsed.get("gaps"),
        },
        "compliance": {
            "checks": compliance["checks"],
            "sources": [
                {
                    "source_document": item.get("source_document"),
                    "section": item.get("section"),
                    "text": item.get("text"),
                    "score": item.get("score"),
                    "chunk_index": item.get("chunk_index"),
                    "language": item.get("language"),
                }
                for item in compliance["sources"]
            ],
        },
    }
