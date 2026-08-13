"""Deterministic output guardrails — run after generate / tool answers.

Enforces CONTEXT-company.md wording even if the model ignored the system prompt.
Validates expected answer format and blocks leaked instructions / sensitive
CONTEXT implementation details before the response reaches the user.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from services.agent.harness.restrictions import (
    ALLERGEN_REFUSAL,
    BAD_FORMAT_REFUSAL,
    COMPANY_STEER_BACK,
    CURRENCY_REFUSAL,
    NO_CONTEXT_ANSWER,
    REASON_ALLERGEN_ABSOLUTE_SAFETY,
    REASON_BAD_OUTPUT_FORMAT,
    REASON_CASUAL_STEER,
    REASON_CURRENCY_CONVERSION,
    REASON_RAG_INTERNALS,
    REASON_SENSITIVE_CONTEXT_LEAK,
    REASON_SYSTEM_PROMPT_LEAK,
    SENSITIVE_CONTEXT_REFUSAL,
    SYSTEM_PROMPT_LEAK_REFUSAL,
    is_casual_general,
    looks_like_bad_answer_format,
    looks_like_sensitive_context_leak,
    looks_like_system_prompt_leak,
    mentions_absolute_allergen_safety,
    mentions_currency_conversion,
    mentions_rag_internals,
)

# Outcomes: allow (unchanged), redact (rewritten, continue), block (hard stop).
OUTCOME_ALLOW = "allow"
OUTCOME_REDACT = "redact"
OUTCOME_BLOCK = "block"


@dataclass(frozen=True, slots=True)
class OutputGuardrailDecision:
    outcome: str
    reason: str | None
    answer: str
    layer: str = "output"

    @property
    def allowed(self) -> bool:
        return self.outcome != OUTCOME_BLOCK

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "outcome": self.outcome,
            "allowed": self.allowed,
            "reason": self.reason,
            "answer": self.answer,
            "layer": self.layer,
        }


def check_output(answer: str | None, *, question: str = "") -> OutputGuardrailDecision:
    """Validate the user-facing answer before it returns to the caller.

    Checks (in order):
    1. Expected format — plain answer string, not raw JSON / memory_proposal
    2. Leaked internal instructions / system prompt → block
    3. Sensitive CONTEXT implementation details (collection, payloads, APIs)
    4. CONTEXT currency / allergen absolute-safety wording
    5. RAG internals (chunks / scores / Qdrant)
    6. Casual/general questions → ensure company steer-back is present
    """
    text = (answer or "").strip()
    if not text:
        return OutputGuardrailDecision(
            outcome=OUTCOME_ALLOW,
            reason=None,
            answer=text,
        )

    if looks_like_bad_answer_format(text):
        return OutputGuardrailDecision(
            outcome=OUTCOME_BLOCK,
            reason=REASON_BAD_OUTPUT_FORMAT,
            answer=BAD_FORMAT_REFUSAL,
        )
    if looks_like_system_prompt_leak(text):
        return OutputGuardrailDecision(
            outcome=OUTCOME_BLOCK,
            reason=REASON_SYSTEM_PROMPT_LEAK,
            answer=SYSTEM_PROMPT_LEAK_REFUSAL,
        )
    if looks_like_sensitive_context_leak(text):
        return OutputGuardrailDecision(
            outcome=OUTCOME_BLOCK,
            reason=REASON_SENSITIVE_CONTEXT_LEAK,
            answer=SENSITIVE_CONTEXT_REFUSAL,
        )
    if mentions_currency_conversion(text):
        return OutputGuardrailDecision(
            outcome=OUTCOME_REDACT,
            reason=REASON_CURRENCY_CONVERSION,
            answer=CURRENCY_REFUSAL,
        )
    if mentions_absolute_allergen_safety(text):
        return OutputGuardrailDecision(
            outcome=OUTCOME_REDACT,
            reason=REASON_ALLERGEN_ABSOLUTE_SAFETY,
            answer=ALLERGEN_REFUSAL,
        )
    if mentions_rag_internals(text):
        cleaned = _strip_rag_internal_sentences(text)
        if not cleaned or cleaned.casefold() == text.casefold():
            cleaned = NO_CONTEXT_ANSWER
        return OutputGuardrailDecision(
            outcome=OUTCOME_REDACT,
            reason=REASON_RAG_INTERNALS,
            answer=cleaned,
        )

    if is_casual_general(question) and COMPANY_STEER_BACK not in text:
        steered = text.rstrip() + " " + COMPANY_STEER_BACK
        return OutputGuardrailDecision(
            outcome=OUTCOME_REDACT,
            reason=REASON_CASUAL_STEER,
            answer=steered,
        )

    return OutputGuardrailDecision(outcome=OUTCOME_ALLOW, reason=None, answer=text)


def _strip_rag_internal_sentences(text: str) -> str:
    parts = [p.strip() for p in text.replace("\n", " ").split(".") if p.strip()]
    kept = [p for p in parts if not mentions_rag_internals(p)]
    if not kept:
        return NO_CONTEXT_ANSWER
    joined = ". ".join(kept)
    if not joined.endswith("."):
        joined += "."
    return joined


def with_answer(decision: OutputGuardrailDecision, answer: str) -> OutputGuardrailDecision:
    return replace(decision, answer=answer)
