"""Deterministic input guardrails — run before tools, RAG, or the LLM.

These are code gates, not prompt suggestions. A jailbreak cannot talk past them.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.agent.harness.restrictions import (
    ALLERGEN_REFUSAL,
    CURRENCY_REFUSAL,
    JAILBREAK_REFUSAL,
    REASON_ALLERGEN_ABSOLUTE_SAFETY,
    REASON_CURRENCY_CONVERSION,
    REASON_JAILBREAK,
    REASON_OFF_TOPIC,
    SCOPE_REFUSAL,
    looks_like_jailbreak,
    looks_off_topic,
    mentions_absolute_allergen_safety,
    mentions_currency_conversion,
)


@dataclass(frozen=True, slots=True)
class InputGuardrailDecision:
    allowed: bool
    reason: str | None
    refusal: str | None
    layer: str = "input"

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "refusal": self.refusal,
            "layer": self.layer,
        }


def check_input(question: str) -> InputGuardrailDecision:
    """Inspect the user turn once, before any model or tool call.

    Order: jailbreak → CONTEXT currency → CONTEXT allergen absolute safety →
    agent scope. Jailbreak wins even when the rest of the text is in-scope.
    """
    text = (question or "").strip()
    if not text:
        return InputGuardrailDecision(allowed=True, reason=None, refusal=None)

    if looks_like_jailbreak(text):
        return InputGuardrailDecision(
            allowed=False,
            reason=REASON_JAILBREAK,
            refusal=JAILBREAK_REFUSAL,
        )
    if mentions_currency_conversion(text):
        return InputGuardrailDecision(
            allowed=False,
            reason=REASON_CURRENCY_CONVERSION,
            refusal=CURRENCY_REFUSAL,
        )
    if mentions_absolute_allergen_safety(text):
        return InputGuardrailDecision(
            allowed=False,
            reason=REASON_ALLERGEN_ABSOLUTE_SAFETY,
            refusal=ALLERGEN_REFUSAL,
        )
    if looks_off_topic(text):
        return InputGuardrailDecision(
            allowed=False,
            reason=REASON_OFF_TOPIC,
            refusal=SCOPE_REFUSAL,
        )
    return InputGuardrailDecision(allowed=True, reason=None, refusal=None)
