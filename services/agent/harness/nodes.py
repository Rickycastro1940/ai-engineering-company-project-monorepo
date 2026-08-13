"""LangGraph nodes for the agent harness: input + output guardrails."""

from __future__ import annotations

import time
from typing import Any

from services.agent.harness.audit import log_guardrail_decision
from services.agent.harness.input import check_input
from services.agent.harness.output import OUTCOME_ALLOW, check_output
from services.agent.harness.restrictions import (
    ACTION_REDIRECT,
    REASON_CASUAL_REDIRECT,
    REASON_SMALL_TALK_REDIRECT,
    casual_general_reply,
)
from services.agent.harness.system_prompt import SMALL_TALK_REPLY
from services.agent.memory.proposal import MemoryProposal
from services.agent.state import AgentState


def _step(
    state: AgentState,
    node_name: str,
    status: str,
    started: float,
    *,
    notes: str | None = None,
    output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "node_name": node_name,
        "sequence": len(state.get("steps") or []) + 1,
        "status": status,
        "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "notes": notes,
        "output": output or {},
    }


def input_guardrail_node(state: AgentState) -> dict[str, Any]:
    """before_agent: block jailbreaks, CONTEXT-forbidden asks, and off-topic."""
    started = time.perf_counter()
    question = state.get("question") or ""
    decision = check_input(question)
    payload = decision.as_dict()
    if not decision.allowed:
        log_guardrail_decision(
            layer="input",
            guardrail="input",
            outcome="block",
            action="block",
            reason=decision.reason,
            question=question,
            detail=payload,
        )
        no_proposal = MemoryProposal.nothing_to_remember(
            f"input_guardrail:{decision.reason}"
        ).as_dict()
        return {
            "answer": decision.refusal,
            "error": None,
            "route": "guardrail_blocked",
            "memory_proposal": no_proposal,
            "guardrail": payload,
            "steps": [
                _step(
                    state,
                    "input_guardrail",
                    "blocked",
                    started,
                    notes=f"blocked:{decision.reason}",
                    output=payload,
                )
            ],
        }
    return {
        "route": "decide",
        "error": None,
        "guardrail": payload,
        "steps": [
            _step(
                state,
                "input_guardrail",
                "ok",
                started,
                notes="input allowed",
                output=payload,
            )
        ],
    }


def answer_small_talk_node(state: AgentState) -> dict[str, Any]:
    """Permitted greeting: hello, then mandatory redirect into CONTEXT domain."""
    started = time.perf_counter()
    question = state.get("question") or ""
    log_guardrail_decision(
        layer="input",
        guardrail="small_talk",
        outcome="redirect",
        action=ACTION_REDIRECT,
        reason=REASON_SMALL_TALK_REDIRECT,
        question=question,
        detail={"answer": SMALL_TALK_REPLY},
    )
    no_proposal = MemoryProposal.nothing_to_remember(
        "permitted_small_talk_not_memorable"
    ).as_dict()
    return {
        "answer": SMALL_TALK_REPLY,
        "error": None,
        "route": "done",
        "memory_proposal": no_proposal,
        "steps": [
            _step(
                state,
                "answer_small_talk",
                "ok",
                started,
                notes="permitted small talk; redirected to Brasaland domain",
                output={"answer": SMALL_TALK_REPLY, "memory_proposal": no_proposal},
            )
        ],
    }


def answer_casual_node(state: AgentState) -> dict[str, Any]:
    """Casual/general ask: brief reply, then steer back to Brasaland context."""
    started = time.perf_counter()
    question = state.get("question") or ""
    answer = casual_general_reply(question)
    log_guardrail_decision(
        layer="input",
        guardrail="casual",
        outcome="redirect",
        action=ACTION_REDIRECT,
        reason=REASON_CASUAL_REDIRECT,
        question=question,
        detail={"answer": answer},
    )
    no_proposal = MemoryProposal.nothing_to_remember(
        "casual_general_not_memorable"
    ).as_dict()
    return {
        "answer": answer,
        "error": None,
        "route": "done",
        "memory_proposal": no_proposal,
        "steps": [
            _step(
                state,
                "answer_casual",
                "ok",
                started,
                notes="casual/general allowed; steered back to Brasaland",
                output={"answer": answer, "memory_proposal": no_proposal},
            )
        ],
    }


def output_guardrail_node(state: AgentState) -> dict[str, Any]:
    """after_agent: enforce CONTEXT wording on the user-facing answer."""
    started = time.perf_counter()
    question = state.get("question") or ""
    original = state.get("answer")
    decision = check_output(original, question=question)
    if decision.outcome != OUTCOME_ALLOW:
        action = "block" if not decision.allowed else ACTION_REDIRECT
        log_guardrail_decision(
            layer="output",
            guardrail="output",
            outcome=decision.outcome,
            action=action,
            reason=decision.reason,
            question=question,
            detail=decision.as_dict(),
        )
    payload = decision.as_dict()
    updates: dict[str, Any] = {
        "answer": decision.answer,
        "guardrail": payload,
        "steps": [
            _step(
                state,
                "output_guardrail",
                "ok" if decision.outcome == OUTCOME_ALLOW else decision.outcome,
                started,
                notes=f"output:{decision.outcome}:{decision.reason or 'ok'}",
                output=payload,
            )
        ],
    }
    if decision.outcome != OUTCOME_ALLOW:
        updates["memory_proposal"] = MemoryProposal.nothing_to_remember(
            f"output_guardrail:{decision.reason}"
        ).as_dict()
        updates["memory_pending_proposal"] = None
    if not decision.allowed:
        updates["route"] = "guardrail_blocked"
        updates["error"] = None
    else:
        updates["route"] = "done"
        updates["error"] = None
    return updates
