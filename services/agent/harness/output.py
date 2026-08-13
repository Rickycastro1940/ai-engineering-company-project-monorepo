"""Deterministic output guardrails — run after generate / tool answers.

Enforces CONTEXT-company.md wording even if the model ignored the system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from services.agent.harness.restrictions import (
    ALLERGEN_REFUSAL,
    CURRENCY_REFUSAL,
    NO_CONTEXT_ANSWER,
    REASON_ALLERGEN_ABSOLUTE_SAFETY,
    REASON_CURRENCY_CONVERSION,
    REASON_RAG_INTERNALS,
    REASON_SYSTEM_PROMPT_LEAK,
    SYSTEM_PROMPT_LEAK_REFUSAL,
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
    """Validate the user-facing answer against CONTEXT restrictions.

    System-prompt leaks are blocked (not merely redacted). Currency conversion
    and absolute allergen claims are replaced with the CONTEXT refusal. RAG
    internals are stripped; if nothing remains, use the unknown-answer phrase.
    """
    del question  # reserved for future model-based checks; unused by rules
    text = (answer or "").strip()
    if not text:
        return OutputGuardrailDecision(
            outcome=OUTCOME_ALLOW,
            reason=None,
            answer=text,
        )

    if looks_like_system_prompt_leak(text):
        return OutputGuardrailDecision(
            outcome=OUTCOME_BLOCK,
            reason=REASON_SYSTEM_PROMPT_LEAK,
            answer=SYSTEM_PROMPT_LEAK_REFUSAL,
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
