"""CONTEXT-company.md restrictions the harness must enforce in code.

Source of truth: repository root ``CONTEXT-company.md``.
These are the company-specific rules the system prompt *and* guardrails
must respect — not a generic safety template.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

CONTEXT_COMPANY_PATH: Final[Path] = Path(__file__).resolve().parents[3] / "CONTEXT-company.md"

# ---------------------------------------------------------------------------
# Agent scope — KB topics + key people + live tools the existing agent already has
# ---------------------------------------------------------------------------
IN_SCOPE_KB_TOPICS: Final[tuple[str, ...]] = (
    "supplier ordering",
    "weekly orders",
    "delivery lead times",
    "minimum protein stock",
    "emergency orders",
    "waste",
    "loyalty",
    "brasa points",
    "allergens",
    "gluten-free",
)

IN_SCOPE_PEOPLE: Final[tuple[str, ...]] = (
    "mariana",
    "felipe guerrero",
    "lucía fernández",
    "lucia fernandez",
)

# Live tools (not memorable, but in-scope for this agent).
IN_SCOPE_LIVE_TOOLS: Final[tuple[str, ...]] = (
    "ticket",
    "incident",
    "inventory",
    "stock",
    "product",
)

# ---------------------------------------------------------------------------
# CONTEXT RAG constraints — enforced on input *and* output
# ---------------------------------------------------------------------------
REASON_CURRENCY_CONVERSION = "context_forbidden_currency_conversion"
REASON_ALLERGEN_ABSOLUTE_SAFETY = "context_forbidden_allergen_absolute_safety"
REASON_UNKNOWN_PLACEHOLDER_AS_FACT = "context_forbidden_unknown_answer_as_fact"
REASON_RAG_INTERNALS = "context_forbidden_rag_chunks_scores_or_qdrant_payloads"
REASON_JAILBREAK = "harness_blocked_prompt_injection"
REASON_OFF_TOPIC = "harness_blocked_out_of_scope"
REASON_SYSTEM_PROMPT_LEAK = "harness_blocked_system_prompt_leak"
REASON_TOOL_WRITE_DENIED = "harness_blocked_tool_write"

NO_CONTEXT_ANSWER = "There is not enough information available."

SCOPE_REFUSAL = (
    "I can only help with Brasaland commercial and operations topics: "
    "supplier ordering, waste protocol, Brasa Points loyalty, menu allergens, "
    "key people (Mariana, Felipe Guerrero, Lucía Fernández), live tickets, "
    "and read-only inventory. "
    + NO_CONTEXT_ANSWER
)

CURRENCY_REFUSAL = (
    "I keep USD $ and COP $ exactly as written and never convert currencies. "
    + NO_CONTEXT_ANSWER
)

ALLERGEN_REFUSAL = (
    "I cannot claim \"zero risk\" or \"100% safe\" for allergens; "
    "I follow the source wording. "
    + NO_CONTEXT_ANSWER
)

JAILBREAK_REFUSAL = (
    "I can't follow instructions that try to override Brasaland operating rules. "
    + NO_CONTEXT_ANSWER
)

SYSTEM_PROMPT_LEAK_REFUSAL = (
    "I can't share internal instructions or system prompts. "
    + NO_CONTEXT_ANSWER
)

TOOL_WRITE_REFUSAL = (
    "Inventory is read-only for this agent. I cannot create, update, or delete "
    "products. "
    + NO_CONTEXT_ANSWER
)

_CURRENCY_CONVERSION = re.compile(
    r"\b(convert(?:s|ed|ing)?|conversion)\b.{0,60}\b(usd|cop|\$)\b"
    r"|\b(usd|cop)\b.{0,60}\b(to|into)\s+(about\s+|approx(?:imately)?\s+)?"
    r".{0,20}\b(usd|cop)\b"
    r"|\b(usd|cop)\b.{0,20}(≈|equals?)\s*.{0,10}\b(usd|cop|\$)\b",
    re.IGNORECASE,
)
_ABSOLUTE_ALLERGEN_SAFETY = re.compile(
    r"\bzero\s+risk\b|\b100%\s*safe\b",
    re.IGNORECASE,
)
_RAG_INTERNALS = re.compile(
    r"\b(chunks?|scores?|qdrant(\s+payloads?)?|payloads?)\b",
    re.IGNORECASE,
)
_JAILBREAK = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above|your)\s+"
    r"(instructions|rules|prompt|guidelines)"
    r"|you\s+are\s+now\s+(dan|jailbroken|unrestricted)"
    r"|jailbreak"
    r"|developer\s+mode"
    r"|system\s+prompt\s+override"
    r"|(reveal|show|print|dump|repeat)\s+(the\s+)?(system\s+)?(prompt|instructions)"
    r"|pretend\s+you\s+have\s+no\s+(rules|restrictions|guardrails)",
    re.IGNORECASE,
)
_SYSTEM_PROMPT_LEAK = re.compile(
    r"(system prompt|STRICT BUSINESS RULES|OUTPUT FORMAT \(single JSON"
    r"|memory_proposal|CONTEXT-company\.md restrictions)",
    re.IGNORECASE,
)
_COMPANY_OR_SCOPE = re.compile(
    r"\b(brasaland|brasa|supplier|order|ordering|protein|emergency|waste"
    r"|loyalty|allergen|allergy|gluten|ticket|incident|inventory|stock"
    r"|product|kg|mariana|felipe|luc[ií]a|fern[aá]ndez|guerrero"
    r"|procurement|points|redemption|menu|dish|remember|remind|approval"
    r"|logging|protocol|escalation|lead\s*time|500\s*usd|ops|operations"
    r"|commercial)\b",
    re.IGNORECASE,
)
_CONFIRMATION_UTTERANCE = re.compile(
    r"^\s*(yes|yep|yeah|ok|okay|sure|please do|go ahead|no|nope|nah"
    r"|don't|do not|cancel|forget it|update it|change it to)\b",
    re.IGNORECASE,
)
_TICKET_ID = re.compile(r"\bBRS-\d+\b", re.IGNORECASE)
_INVENTORY_WRITE_ACTION = re.compile(
    r"\b(create|update|delete|insert|upsert|patch|put|write|remove)\b",
    re.IGNORECASE,
)


def context_company_text() -> str:
    return CONTEXT_COMPANY_PATH.read_text(encoding="utf-8")


def mentions_currency_conversion(text: str) -> bool:
    return bool(_CURRENCY_CONVERSION.search(text or ""))


def mentions_absolute_allergen_safety(text: str) -> bool:
    return bool(_ABSOLUTE_ALLERGEN_SAFETY.search(text or ""))


def mentions_rag_internals(text: str) -> bool:
    return bool(_RAG_INTERNALS.search(text or ""))


def looks_like_jailbreak(text: str) -> bool:
    return bool(_JAILBREAK.search(text or ""))


def looks_like_system_prompt_leak(text: str) -> bool:
    return bool(_SYSTEM_PROMPT_LEAK.search(text or ""))


def is_confirmation_utterance(text: str) -> bool:
    stripped = (text or "").strip()
    if len(stripped) > 160:
        return False
    return bool(_CONFIRMATION_UTTERANCE.match(stripped))


def in_agent_scope(text: str) -> bool:
    """True when the turn is in-scope for this Brasaland support agent.

    In-scope includes CONTEXT KB topics, key people, live ticket/inventory
    tools, memory confirmation, and any question that names Brasaland.
    Out-of-scope is everything else (other companies, general coding, etc.).
    """
    q = text or ""
    if is_confirmation_utterance(q):
        return True
    if _TICKET_ID.search(q):
        return True
    if _COMPANY_OR_SCOPE.search(q):
        return True
    return False


def looks_off_topic(text: str) -> bool:
    """Default-deny: anything outside Brasaland agent scope is off-topic."""
    if in_agent_scope(text):
        return False
    return True


def inventory_write_attempt(tool_name: str, arguments: dict[str, object] | None) -> bool:
    name = (tool_name or "").casefold()
    args = arguments or {}
    if "inventory" not in name:
        # Explicit write verbs on any tool whose name is inventory-related.
        return False
    action = str(args.get("action") or args.get("method") or "")
    if _INVENTORY_WRITE_ACTION.search(action):
        return True
    for key in ("quantity", "new_quantity", "delete", "create", "update"):
        value = args.get(key)
        if key in ("delete", "create", "update") and value not in (None, False, "", 0):
            return True
        if key in ("quantity", "new_quantity") and args.get("action"):
            if _INVENTORY_WRITE_ACTION.search(str(args.get("action"))):
                return True
    write_fields = ("new_name", "new_unit", "set_quantity", "payload")
    return any(args.get(field) not in (None, "", False) for field in write_fields)
