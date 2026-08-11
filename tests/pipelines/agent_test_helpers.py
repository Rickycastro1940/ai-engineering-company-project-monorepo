"""Shared helpers for agent pipeline tests."""

from __future__ import annotations

from services.agent.memory.proposal import AgentTurnOutput, MemoryProposal

GROUNDED_ANSWER = (
    "Every Brasaland location must keep at least 3 days of main protein inventory. "
    "Emergency orders over 500 USD need approval from Lucía Fernández."
)


def agent_turn(
    answer: str,
    *,
    applicable: bool = False,
    action: str | None = None,
    fact: str | None = None,
    previous_fact: str | None = None,
    why: str | None = None,
) -> AgentTurnOutput:
    """Structured generate output for mocks (answer + memory_proposal)."""
    return AgentTurnOutput(
        answer=answer,
        memory_proposal=MemoryProposal(
            applicable=applicable,
            action=action,  # type: ignore[arg-type]
            fact=fact,
            previous_fact=previous_fact,
            why=why,
        ),
    )


def grounded_turn(answer: str = GROUNDED_ANSWER) -> AgentTurnOutput:
    """Default RAG mock: grounded answer + supplier-ordering memory proposal."""
    return agent_turn(
        answer,
        applicable=True,
        action="add",
        fact="Locations must keep at least 3 days of main protein inventory.",
        why="New durable supplier-ordering fact from grounded KB context.",
    )
