"""Deterministic input guardrails — run before tools, RAG, or the LLM.

These are code gates, not prompt suggestions. A jailbreak cannot talk past them.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.agent.harness.restrictions import (
    ALLERGEN_REFUSAL,
    CURRENCY_REFUSAL,
    JAILBREAK_REFUSAL,
    PERSONAL_USE_REFUSAL,
    REASON_ALLERGEN_ABSOLUTE_SAFETY,
    REASON_CURRENCY_CONVERSION,
    REASON_JAILBREAK,
    REASON_OFF_TOPIC,
    REASON_PERSONAL_USE,
    SCOPE_REFUSAL,
    is_instruction_change_request,
    is_personal_use_request,
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


def reject_instruction_change(question: str) -> InputGuardrailDecision | None:
    """Explicit rejection for instruction-change / jailbreak requests.

    Covers the three documented rephrasings in ``INSTRUCTION_CHANGE_VARIANTS``
    plus related patterns (ignore previous instructions, developer mode, …).
    Returns a block decision, or ``None`` when the turn is not an
    instruction-change attempt.
    """
    if is_instruction_change_request(question or ""):
        return InputGuardrailDecision(
            allowed=False,
            reason=REASON_JAILBREAK,
            refusal=JAILBREAK_REFUSAL,
        )
    return None


def check_input(question: str) -> InputGuardrailDecision:
    """Inspect the user turn once, before any model or tool call.

    Order: instruction-change / jailbreak → CONTEXT currency → CONTEXT allergen
    absolute safety → personal/non-company use → hard out-of-scope.
    Casual/general questions are allowed through (steered back later).
    Instruction-change wins even when the rest of the text looks in-scope.
    """
    text = (question or "").strip()
    if not text:
        return InputGuardrailDecision(allowed=True, reason=None, refusal=None)

    blocked = reject_instruction_change(text)
    if blocked is not None:
        return blocked
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
    if is_personal_use_request(text):
        return InputGuardrailDecision(
            allowed=False,
            reason=REASON_PERSONAL_USE,
            refusal=PERSONAL_USE_REFUSAL,
        )
    if looks_off_topic(text):
        return InputGuardrailDecision(
            allowed=False,
            reason=REASON_OFF_TOPIC,
            refusal=SCOPE_REFUSAL,
        )
    return InputGuardrailDecision(allowed=True, reason=None, refusal=None)
