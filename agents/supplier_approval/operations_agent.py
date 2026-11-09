"""Operations Agent — approval summary for management.

Restaurant Operations writes the note. Lucía Fernández (Procurement) is the
reader who decides whether the supplier enters the directory for both markets.
"""

from __future__ import annotations

from agents.supplier_approval.groq_client import maybe_refine_summary

_DECISION_LINE = {
    "approve": "Approve this supplier for new orders.",
    "approve_with_conditions": "Approve this supplier only after the conditions below are closed.",
    "reject": "Do not approve this supplier.",
}


def decide(parsed: dict, checks: list[dict]) -> tuple[str, list[str]]:
    if not parsed.get("complete"):
        return "reject", list(parsed.get("gaps") or ["The application is incomplete."])
    if parsed.get("status") == "inactive":
        return "reject", ["Applicant status is inactive, so kitchens must not place new orders."]
    failures = [item["detail"] for item in checks if item["status"] == "fail"]
    if failures:
        return "reject", failures
    conditions = [item["detail"] for item in checks if item["status"] == "condition"]
    if conditions:
        return "approve_with_conditions", conditions
    return "approve", []


def render_summary(parsed: dict, decision: str, conditions: list[str], citations: list[dict]) -> str:
    categories = ", ".join(parsed.get("categories") or []) or "no category"
    lines = [
        "Supplier approval summary for Brasaland management.",
        "Prepared by Restaurant Operations for Lucía Fernández (Procurement).",
        f"Applicant: {parsed.get('name') or 'Unnamed applicant'}.",
        f"Market: {parsed.get('market') or 'unknown market'}. Currency: {parsed.get('currency') or 'unspecified currency'}.",
        f"Categories: {categories}.",
        _DECISION_LINE[decision],
    ]
    if conditions:
        lines.append("Conditions:")
        lines.extend(f"- {item}" for item in conditions)
    if citations:
        lines.append("Standards cited from the Brasaland knowledge base:")
        lines.extend(
            f"- {item.get('source_document')} ({item.get('section')})"
            for item in citations
        )
    else:
        lines.append("No knowledge-base standard was cited.")
    return "\n".join(lines)


def run(state: dict) -> dict:
    parsed = state["parsed"]
    compliance = state["compliance"]
    decision, conditions = decide(parsed, compliance["checks"])
    summary = render_summary(parsed, decision, conditions, compliance["sources"])
    summary, llm = maybe_refine_summary(summary, decision)
    state["decision"] = decision
    state["conditions"] = conditions
    state["summary"] = summary
    state["llm"] = llm
    state["trace"].append("operations")
    return state
