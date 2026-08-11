"""Structured memory proposal from the same agent generate call.

Not a second model call or a separate agent — one additional output field
alongside the user-facing ``answer``.

Most interactions must be dismissible as nothing to remember
(``applicable=false``). See ``NOTHING_TO_REMEMBER_EXAMPLES`` and
``docs/agent/MEMORY_SELF_EVAL.md``.
"""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class NothingToRememberExample(TypedDict):
    id: str
    user: str
    why_dismiss: str
    why_code: str


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
    """

    model_config = ConfigDict(extra="forbid")

    applicable: bool = Field(
        False,
        description="True only when something new or corrected is worth remembering.",
    )
    action: Literal["add", "change"] | None = Field(
        None,
        description="add = new fact; change = correct/replace an existing fact.",
    )
    fact: str | None = Field(
        None,
        description="The fact text to store (added or corrected wording).",
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
