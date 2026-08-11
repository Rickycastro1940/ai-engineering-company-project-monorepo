"""Explicit confirmation-intent classification for a pending memory proposal.

Does **not** approve merely because the substring ``yes`` appears. Labels are
structured outcomes from ordered criteria.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

from services.agent.memory.pending import PendingProposal


class ConfirmationIntent(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    TOPIC_CHANGE = "topic_change"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class IntentClassification:
    intent: ConfirmationIntent
    reason: str
    residual_question: str | None = None
    edited_fact: str | None = None

    def as_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "reason": self.reason,
            "residual_question": self.residual_question,
            "edited_fact": self.edited_fact,
        }


# Affirmation / rejection as *primary speech act* (not substring presence alone).
_APPROVE_ONLY = re.compile(
    r"^\s*(yes|yep|yeah|yup|sure|ok|okay|please\s+do|go\s+ahead|"
    r"affirmative|correct|sounds?\s+good|please\s+remember(\s+it)?|"
    r"remember\s+it|save\s+it|do\s+it)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_APPROVE_PREFIX = re.compile(
    r"^\s*(yes|yep|yeah|sure|ok|okay|please\s+do|go\s+ahead|"
    r"please\s+remember(\s+it)?|remember\s+it|save\s+it)\s*[,—\-\.:!]+\s+",
    re.IGNORECASE,
)
_REJECT_ONLY = re.compile(
    r"^\s*(no|nope|nah|don'?t|do\s+not|skip(\s+it)?|discard(\s+it)?|"
    r"never\s+mind|no\s+thanks|cancel|forget\s+it)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_REJECT_PREFIX = re.compile(
    r"^\s*(no|nope|don'?t|do\s+not|skip(\s+it)?|discard(\s+it)?|"
    r"never\s+mind|no\s+thanks|cancel|forget\s+it)\s*[,—\-\.:!]+\s+",
    re.IGNORECASE,
)
_EDIT = re.compile(
    r"(?is)^\s*(?:actually[, ]+|instead[, ]+|change\s+it\s+to\s+|remember\s+"
    r"(?:this|that)\s+instead\s*[:\-]?\s*|edit\s*(?:to|:)\s*|correct\s+it\s+to\s+)"
    r"(.+)$"
)
_TOPIC_MARKERS: Final[tuple[str, ...]] = (
    "ticket",
    "brs-",
    "inventory",
    "stock",
    "allergen",
    "waste",
    "loyalty",
    "brasa points",
    "what is",
    "what's",
    "how many",
    "how much",
    "when is",
    "who is",
    "where is",
    "status of",
)


def classify_confirmation_intent(
    message: str,
    pending: PendingProposal | None,
) -> IntentClassification:
    """Return an explicit intent label for the user message given a pending proposal.

    Ordered criterion (first match wins after edit check):
    1. No pending → AMBIGUOUS (nothing to confirm)
    2. EDIT patterns with a replacement fact
    3. Pure REJECT / REJECT+residual → REJECT
    4. Pure APPROVE / APPROVE+residual → APPROVE
    5. Message looks like a new domain question without a clear speech-act
       approve/reject → TOPIC_CHANGE (pending discarded by default)
    6. Else AMBIGUOUS (pending discarded by default — never assume approval)
    """
    text = (message or "").strip()
    if pending is None:
        return IntentClassification(
            intent=ConfirmationIntent.AMBIGUOUS,
            reason="no_pending_proposal",
        )
    if not text:
        return IntentClassification(
            intent=ConfirmationIntent.AMBIGUOUS,
            reason="empty_message_default_discard",
        )

    edit_match = _EDIT.match(text)
    if edit_match:
        edited = edit_match.group(1).strip().strip('"').strip("'")
        if edited:
            return IntentClassification(
                intent=ConfirmationIntent.EDIT,
                reason="explicit_edit_pattern",
                edited_fact=edited,
            )

    if _REJECT_ONLY.match(text):
        return IntentClassification(
            intent=ConfirmationIntent.REJECT,
            reason="explicit_reject_utterance",
        )
    reject_prefix = _REJECT_PREFIX.match(text)
    if reject_prefix:
        residual = text[reject_prefix.end() :].strip()
        return IntentClassification(
            intent=ConfirmationIntent.REJECT,
            reason="explicit_reject_prefix_with_residual",
            residual_question=residual or None,
        )

    if _APPROVE_ONLY.match(text):
        return IntentClassification(
            intent=ConfirmationIntent.APPROVE,
            reason="explicit_approve_utterance",
        )
    approve_prefix = _APPROVE_PREFIX.match(text)
    if approve_prefix:
        residual = text[approve_prefix.end() :].strip()
        return IntentClassification(
            intent=ConfirmationIntent.APPROVE,
            reason="explicit_approve_prefix_with_residual",
            residual_question=residual or None,
        )

    lowered = text.casefold()
    # Substring "yes" alone is insufficient — require topic markers for TOPIC_CHANGE.
    if any(marker in lowered for marker in _TOPIC_MARKERS) and "?" in text:
        return IntentClassification(
            intent=ConfirmationIntent.TOPIC_CHANGE,
            reason="new_question_without_explicit_confirmation_speech_act",
            residual_question=text,
        )
    if any(marker in lowered for marker in _TOPIC_MARKERS) and not re.search(
        r"\b(yes|yep|yeah|sure|ok|okay|no|nope)\b", lowered
    ):
        return IntentClassification(
            intent=ConfirmationIntent.TOPIC_CHANGE,
            reason="topic_shift_without_confirmation_speech_act",
            residual_question=text,
        )

    return IntentClassification(
        intent=ConfirmationIntent.AMBIGUOUS,
        reason="no_explicit_approve_reject_or_edit_default_discard",
    )
