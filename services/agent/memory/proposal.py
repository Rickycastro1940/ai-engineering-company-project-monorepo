"""Structured memory proposal from the same agent generate call.

Not a second model call or a separate agent — one additional output field
alongside the user-facing ``answer``.

Most interactions must be dismissible as nothing to remember
(``applicable=false``). See ``MEMORABLE_INTERACTION_EXAMPLES``,
``NOTHING_TO_REMEMBER_EXAMPLES``, and ``docs/agent/MEMORY_SELF_EVAL.md``.
"""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class NothingToRememberExample(TypedDict):
    id: str
    user: str
    why_dismiss: str
    why_code: str


class MemorableInteractionExample(TypedDict):
    id: str
    user: str
    why_remember: str
    expected_fact: str
    kind: str

# At least three documented interactions that SHOULD generate a proposal.
# Keep in sync with docs/agent/MEMORY_SELF_EVAL.md.
MEMORABLE_INTERACTION_EXAMPLES: Final[tuple[MemorableInteractionExample, ...]] = (
    {
        "id": "protein_stock_days",
        "user": (
            "How many days of main protein inventory should each location keep?"
        ),
        "why_remember": (
            "Durable supplier-ordering procedure from CONTEXT KB."
        ),
        "expected_fact": "Locations must keep 3 days of main protein inventory.",
        "kind": "supplier_ordering",
    },
    {
        "id": "waste_escalation_owner",
        "user": (
            "Who handles waste escalation when we exceed the daily threshold?"
        ),
        "why_remember": (
            "Durable waste + key-person fact (Felipe Guerrero) from CONTEXT."
        ),
        "expected_fact": (
            "Waste over the daily escalation threshold is handled by "
            "Felipe Guerrero (Operations Director)."
        ),
        "kind": "people",
    },
    {
        "id": "emergency_order_approval",
        "user": "When do emergency orders need approval?",
        "why_remember": (
            "Durable procurement rule; currency kept as written (never convert)."
        ),
        "expected_fact": (
            "Emergency orders over 500 USD require Procurement Manager "
            "(Lucía Fernández) approval."
        ),
        "kind": "supplier_ordering",
    },
)


# At least three documented interactions that must NOT generate a proposal.
# Keep in sync with docs/agent/MEMORY_SELF_EVAL.md.
NOTHING_TO_REMEMBER_EXAMPLES: Final[tuple[NothingToRememberExample, ...]] = (
    {
        "id": "ticket_status",
        "user": "What is the status of ticket BRS-000002?",
        "why_dismiss": (
            "Incident rows are live MCP/tool state, not a CONTEXT memorable domain."
        ),
        "why_code": "ticket_path_not_in_context_memorable_domains",
    },
    {
        "id": "inventory_quantity",
        "user": "How many kg of tomatoes are in stock?",
        "why_dismiss": (
            "Inventory quantities change constantly; raw product rows are not "
            "CONTEXT memorable topics."
        ),
        "why_code": "inventory_path_not_in_context_memorable_domains",
    },
    {
        "id": "unknown_answer",
        "user": "What is Brasaland's secret sauce recipe?",
        "why_dismiss": (
            "Unknown-answer placeholder must not be learned; no grounded KB fact."
        ),
        "why_code": "unknown_answer_must_not_be_learned",
    },
)


class MemoryProposal(BaseModel):
    """What would be added or changed in durable memory, and why.

    ``applicable=false`` (or omitted action/fact) means nothing worth remembering
    after this interaction — the agent must not always propose a write.

    When applicable, the agent asks the user in the response (proposal question).
    It does **not** write to durable memory on the same step.
    """

    model_config = ConfigDict(extra="forbid")

    applicable: bool = Field(
        False,
        description="True only when something new or corrected is worth proposing.",
    )
    action: Literal["add", "change"] | None = Field(
        None,
        description="add = new fact; change = correct/replace an existing fact.",
    )
    fact: str | None = Field(
        None,
        description="The fact text to propose (added or corrected wording).",
    )
    previous_fact: str | None = Field(
        None,
        description="Existing remembered fact being changed (action=change only).",
    )
    why: str | None = Field(
        None,
        description="Brief reason: why this is new/corrected, or why nothing to remember.",
    )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def nothing_to_remember(cls, why_code: str) -> MemoryProposal:
        """Standard dismiss proposal (applicable=false)."""
        return cls(applicable=False, why=why_code)

    def user_facing_question(self) -> str | None:
        """Closing question for the user response, or None if not applicable."""
        if not self.applicable or not (self.fact or "").strip():
            return None
        fact = self.fact.strip()
        if self.action == "change":
            if self.previous_fact:
                return (
                    f'Would you like me to update what I remember from '
                    f'"{self.previous_fact.strip()}" to "{fact}"?'
                )
            return f'Would you like me to update what I remember to: "{fact}"?'
        return f'Would you like me to remember this for later: "{fact}"?'


def attach_proposal_question_to_answer(answer: str, proposal: MemoryProposal) -> str:
    """Append the memory-proposal question to the user-facing answer when applicable.

    Idempotent if a similar question is already present. Never persists memory.
    """
    question = proposal.user_facing_question()
    if not question:
        return answer
    lowered = (answer or "").casefold()
    if "would you like me to remember" in lowered or "would you like me to update what i remember" in lowered:
        return answer
    base = (answer or "").rstrip()
    if not base:
        return question
    return f"{base}\n\n{question}"


class AgentTurnOutput(BaseModel):
    """Single-call structured output: user answer + optional memory proposal."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., description="User-facing answer only (no memory JSON).")
    memory_proposal: MemoryProposal = Field(
        default_factory=MemoryProposal,
        description="Self-evaluation: add/change/why if applicable; else applicable=false.",
    )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def answer_with_proposal_question(self) -> str:
        """User-visible answer including the optional remember/update question."""
        return attach_proposal_question_to_answer(self.answer, self.memory_proposal)
