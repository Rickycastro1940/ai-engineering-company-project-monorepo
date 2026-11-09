"""LangGraph for the Brasaland supplier-approval handoff.

Three nodes share one state object, in order:

1. Supplier parses the application.
2. Compliance checks health standards only when a retrieved chunk states them.
3. Operations writes approve / approve with conditions / reject.

Groq still rewrites only the operations narrative, inside the operations node,
when ``BRASALAND_SUPPLIER_AGENTS=groq``.
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.supplier_approval import compliance_agent, operations_agent, supplier_agent


class SupplierApprovalState(TypedDict, total=False):
    input: dict
    trace: list
    parsed: Optional[dict]
    compliance: Optional[dict]
    decision: Optional[str]
    conditions: list
    summary: Optional[str]
    llm: str


def _copy_state(state: SupplierApprovalState) -> dict[str, Any]:
    """Give each node its own dict so in-place updates stay on that step."""
    return {
        "input": state.get("input") or {},
        "trace": list(state.get("trace") or []),
        "parsed": state.get("parsed"),
        "compliance": state.get("compliance"),
        "decision": state.get("decision"),
        "conditions": list(state.get("conditions") or []),
        "summary": state.get("summary"),
        "llm": state.get("llm") or "not_used",
    }


def supplier_node(state: SupplierApprovalState) -> dict[str, Any]:
    return supplier_agent.run(_copy_state(state))


def compliance_node(state: SupplierApprovalState) -> dict[str, Any]:
    return compliance_agent.run(_copy_state(state))


def operations_node(state: SupplierApprovalState) -> dict[str, Any]:
    return operations_agent.run(_copy_state(state))


def build_supplier_approval_graph():
    graph = StateGraph(SupplierApprovalState)
    graph.add_node("supplier", supplier_node)
    graph.add_node("compliance", compliance_node)
    graph.add_node("operations", operations_node)
    graph.set_entry_point("supplier")
    graph.add_edge("supplier", "compliance")
    graph.add_edge("compliance", "operations")
    graph.add_edge("operations", END)
    return graph.compile()


supplier_approval_graph = build_supplier_approval_graph()
