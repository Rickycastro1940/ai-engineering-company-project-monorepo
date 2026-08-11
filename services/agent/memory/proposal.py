"""Structured memory proposal from the same agent generate call.

Not a second model call or a separate agent — one additional output field
alongside the user-facing ``answer``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
        description="Brief reason: why this is new or a correction.",
    )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


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
