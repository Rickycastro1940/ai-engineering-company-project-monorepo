"""Evaluate: out-of-domain queries redirect into Brasaland CONTEXT.

The secured agent must not behave like a general-purpose assistant on
off-domain asks. Every out-of-domain path either refuses + redirects to the
company purpose, or (for brief casual asks) steers back into CONTEXT topics.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from services.agent.graph import compile_agent_graph, run_agent
from services.agent.harness.input import check_input
from services.agent.harness.output import check_output
from services.agent.harness.restrictions import (
    AGENT_PURPOSE,
    COMPANY_STEER_BACK,
    PERSONAL_USE_REFUSAL,
    REASON_OFF_TOPIC,
    REASON_PERSONAL_USE,
    SCOPE_REFUSAL,
    casual_general_reply,
)
from services.agent.harness.system_prompt import SMALL_TALK_REPLY
from services.agent.tracing import load_trace

# Company-context markers that must appear in redirects (not a general chatbot).
_COMPANY_MARKERS = (
    "brasaland",
    "supplier ordering",
    "brasa points",
)


def _assert_redirects_to_company(text: str) -> None:
    lowered = (text or "").casefold()
    assert "brasaland" in lowered
    assert any(m in lowered for m in ("supplier ordering", "waste", "brasa points", "allergen"))
    # Must not look like a fulfilled general-purpose answer.
    assert "once upon a time" not in lowered
    assert "dear love" not in lowered


def _run(question: str, trace_dir: Path, **node_patches) -> dict:
    patchers = []
    for target, value in node_patches.items():
        p = patch(target, value)
        patchers.append(p)
        p.start()
    try:
        with patch("services.agent.tracing.DEFAULT_TRACE_DIR", trace_dir), patch(
            "services.agent.graph.save_trace"
        ) as mock_save:
            from services.agent.tracing import save_trace as real_save

            mock_save.side_effect = lambda record, **_: real_save(
                record, trace_dir=trace_dir
            )
            with patch("services.agent.graph._COMPILED_GRAPH", compile_agent_graph()):
                return run_agent(question)
    finally:
        for p in reversed(patchers):
            p.stop()


def test_hard_out_of_domain_is_refused_with_company_redirect() -> None:
    """Hard off-topic: decline and point back to Brasaland purpose (no LLM answer)."""
    for question in (
        "Explain quantum entanglement in detail.",
        "Who won the World Cup in 2018?",
        "Plan my vacation itinerary for Iceland next summer.",
    ):
        decision = check_input(question)
        assert decision.allowed is False, question
        assert decision.reason == REASON_OFF_TOPIC, question
        assert decision.refusal == SCOPE_REFUSAL
        _assert_redirects_to_company(decision.refusal)
        assert AGENT_PURPOSE.casefold() in decision.refusal.casefold()


def test_personal_non_company_use_redirects_to_company_purpose() -> None:
    """Personal asks are declined; response names the Brasaland agent purpose."""
    for question in (
        "write me a love poem",
        "help me with my university homework",
        "Write me a Python script to scrape competitor menus.",
    ):
        decision = check_input(question)
        assert decision.allowed is False, question
        assert decision.reason == REASON_PERSONAL_USE, question
        assert decision.refusal == PERSONAL_USE_REFUSAL
        _assert_redirects_to_company(decision.refusal)
        assert "can't help with personal" in decision.refusal.casefold()


def test_casual_general_steers_back_to_company_context() -> None:
    """Casual world questions may get a brief reply, then must steer to CONTEXT."""
    for question in (
        "what time is it in Tokyo?",
        "What is the capital of France?",
    ):
        assert check_input(question).allowed is True, question
        reply = casual_general_reply(question)
        assert COMPANY_STEER_BACK in reply
        _assert_redirects_to_company(reply)
        # Not a full general-assistant answer (no invented city facts as the close).
        assert "paris is the capital" not in reply.casefold()


def test_small_talk_redirects_into_brasaland_domain() -> None:
    _assert_redirects_to_company(SMALL_TALK_REPLY)
    assert "what do you need" in SMALL_TALK_REPLY.casefold()


def test_graph_out_of_domain_never_calls_generate(tmp_path: Path) -> None:
    """Graph evidence: out-of-domain turns never reach the LLM generate node."""
    trace_dir = tmp_path / "traces"
    cases = [
        ("Explain quantum entanglement in detail.", SCOPE_REFUSAL, ["receive_question", "input_guardrail"]),
        ("write me a love poem", PERSONAL_USE_REFUSAL, ["receive_question", "input_guardrail"]),
        (
            "what time is it in Tokyo?",
            casual_general_reply("what time is it in Tokyo?"),
            [
                "receive_question",
                "input_guardrail",
                "resolve_memory_confirmation",
                "decide_route",
                "answer_casual",
            ],
        ),
        (
            "hello",
            SMALL_TALK_REPLY,
            [
                "receive_question",
                "input_guardrail",
                "resolve_memory_confirmation",
                "decide_route",
                "answer_small_talk",
            ],
        ),
    ]
    with patch("services.agent.nodes.generate_agent_turn") as mock_generate, patch(
        "services.agent.nodes.retrieve"
    ) as mock_retrieve:
        for question, expected_answer, expected_order in cases:
            result = _run(question, trace_dir)
            assert result["node_order"] == expected_order, question
            assert result["answer"] == expected_answer, question
            _assert_redirects_to_company(result["answer"] or "")
            # Never a general-purpose free-form completion path.
            assert "generate" not in result["node_order"]
            assert "retrieve" not in result["node_order"]
            trace = load_trace(result["trace_id"], trace_dir=trace_dir)
            assert "generate" not in trace["node_order"]
    mock_generate.assert_not_called()
    mock_retrieve.assert_not_called()


def test_in_domain_still_allowed_through_to_agent_path() -> None:
    """Control: company questions are not treated as out-of-domain redirects."""
    for question in (
        "What is the minimum stock rule for proteins?",
        "status of ticket BRS-000002",
        "Do we have stock of tomatoes?",
        "When do emergency orders need Lucía Fernández's approval?",
    ):
        assert check_input(question).allowed is True, question


def test_output_steer_appends_company_context_for_casual() -> None:
    """If a casual answer somehow lacks steer-back, output guardrail adds it."""
    steered = check_output(
        "Tokyo is usually UTC+9.",
        question="what time is it in Tokyo?",
    )
    assert COMPANY_STEER_BACK in steered.answer
    _assert_redirects_to_company(steered.answer)
