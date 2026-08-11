"""Agent generation: one model call → answer + optional memory_proposal.

Reuses Brasaland RAG grounding rules from ``data.pipelines.rag`` (same system
constraints). This is **not** a second LLM call, separate agent, or multi-agent
setup — only structured output with one extra field.
"""

from __future__ import annotations

import json
from typing import Any

from data.pipelines.rag import (
    GENERATION_MODEL,
    NO_CONTEXT_ANSWER,
    SYSTEM_PROMPT,
    _format_context,
    client,
)

from services.agent.memory.proposal import AgentTurnOutput, MemoryProposal
from services.agent.memory.store import MemoryRecord

# Appended to the shared SYSTEM_PROMPT for the agent turn only.
STRUCTURED_TURN_INSTRUCTIONS = """
OUTPUT FORMAT (single JSON object — no markdown fences):
{
  "answer": "<user-facing answer string only>",
  "memory_proposal": {
    "applicable": false,
    "action": null,
    "fact": null,
    "previous_fact": null,
    "why": null
  }
}

MEMORY SELF-EVALUATION (memory_proposal) — same call, not a second pass:
- Decide whether anything is NEW or a CORRECTION worth remembering. Do not always propose memory.
- Default: applicable=false (nothing to remember). A proposal is the exception.
- applicable=true only for durable Brasaland ops/commercial facts from CONTEXT domains:
  supplier ordering, waste, loyalty (Brasa Points), allergens, key people
  (Mariana, Felipe Guerrero, Lucía Fernández).
- action="add" when the fact is new; action="change" when it corrects something in
  "Existing agent memory" (set previous_fact to that text).
- fact = the concise fact to store (not the full answer, not chunks/scores/payloads).
- why = short reason (new vs corrected), or why nothing to remember.
- MUST set applicable=false (nothing to remember) for at least these cases:
  1) live ticket status lookups (e.g. "status of ticket BRS-000002")
  2) live inventory quantity lookups (e.g. "how many kg of tomatoes")
  3) unknown answers ("There is not enough information available.")
  4) duplicates of facts already listed under Existing agent memory
- NEVER propose currency conversion, "zero risk", "100% safe", or the unknown-answer phrase.
- "answer" must remain the clean user-facing response (no memory_proposal JSON inside it).
"""


def _format_recalled(records: list[MemoryRecord]) -> str:
    if not records:
        return "(none)"
    lines = [f"- [{r.kind}] {r.text}" for r in records]
    return "\n".join(lines)


def generate_agent_turn(
    question: str,
    context: list[dict[str, Any]] | str,
    *,
    recalled: list[MemoryRecord] | None = None,
) -> AgentTurnOutput:
    """One chat completion → ``answer`` + ``memory_proposal``.

    Does not call ``retrieve``. Same grounding rules as ``generate_answer``.
    """
    if isinstance(context, list):
        if not context:
            return AgentTurnOutput(
                answer=NO_CONTEXT_ANSWER,
                memory_proposal=MemoryProposal(applicable=False, why="no_retrieved_context"),
            )
        context_str = _format_context(context)
    else:
        context_str = (context or "").strip()
        if not context_str:
            return AgentTurnOutput(
                answer=NO_CONTEXT_ANSWER,
                memory_proposal=MemoryProposal(applicable=False, why="no_retrieved_context"),
            )

    recalled = recalled or []
    user_prompt = (
        f"Context:\n{context_str}\n\n"
        f"Existing agent memory (from MemoryInterface.read — do not dump invent):\n"
        f"{_format_recalled(recalled)}\n\n"
        f"Question: {question}"
    )
    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT + "\n" + STRUCTURED_TURN_INSTRUCTIONS,
            },
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    return parse_agent_turn_json(raw)


def parse_agent_turn_json(raw: str) -> AgentTurnOutput:
    """Parse model JSON into ``AgentTurnOutput``; fall back safely on bad shape."""
    if not raw:
        return AgentTurnOutput(
            answer=NO_CONTEXT_ANSWER,
            memory_proposal=MemoryProposal(applicable=False, why="empty_model_output"),
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Model ignored JSON — treat whole string as user answer; no proposal.
        return AgentTurnOutput(
            answer=raw,
            memory_proposal=MemoryProposal(
                applicable=False, why="unparseable_json_no_proposal"
            ),
        )
    if not isinstance(data, dict):
        return AgentTurnOutput(
            answer=str(data),
            memory_proposal=MemoryProposal(applicable=False, why="non_object_json"),
        )
    answer = str(data.get("answer") or "").strip() or NO_CONTEXT_ANSWER
    proposal_raw = data.get("memory_proposal")
    try:
        if proposal_raw is None:
            proposal = MemoryProposal(applicable=False, why="omitted_memory_proposal")
        elif isinstance(proposal_raw, dict):
            proposal = MemoryProposal.model_validate(proposal_raw)
        else:
            proposal = MemoryProposal(applicable=False, why="invalid_memory_proposal_shape")
    except Exception:  # noqa: BLE001
        proposal = MemoryProposal(applicable=False, why="memory_proposal_validation_failed")

    # Normalize: applicable without fact/action → not applicable.
    if proposal.applicable and (not proposal.fact or not proposal.action):
        proposal = MemoryProposal(
            applicable=False,
            why=proposal.why or "applicable_without_action_or_fact",
        )
    return AgentTurnOutput(answer=answer, memory_proposal=proposal)
