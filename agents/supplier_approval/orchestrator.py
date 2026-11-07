"""Collaborative supplier-approval handoff.

Three roles share one state object, in order:

1. Supplier Agent parses the application.
2. Compliance Agent checks health and ordering standards in the knowledge base.
3. Operations Agent writes the approval summary for management.

LangGraph and CrewAI are not used. The monorepo agent loop is plain Python
on the Groq client (`agent.py`), and those frameworks are not installed.
This handoff is the same shape: each role reads the previous role's output
and appends its own. Groq rewrites only the operations narrative when
`BRASALAND_SUPPLIER_AGENTS=groq`.
"""

from __future__ import annotations

from agents.supplier_approval import compliance_agent, operations_agent, supplier_agent

ROLES = ("supplier", "compliance", "operations")


def review_supplier_application(payload: dict) -> dict:
    state = {
        "input": payload or {},
        "trace": [],
        "parsed": None,
        "compliance": None,
        "decision": None,
        "conditions": [],
        "summary": None,
        "llm": "not_used",
    }
    state = supplier_agent.run(state)
    state = compliance_agent.run(state)
    state = operations_agent.run(state)
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
        "orchestration": "plain-python-handoff",
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
