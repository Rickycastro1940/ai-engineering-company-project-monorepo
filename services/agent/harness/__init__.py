"""Brasaland agent harness: system prompt + deterministic guardrails."""

from services.agent.harness.external import (
    UNTRUSTED_MEMORY_CLOSE,
    UNTRUSTED_MEMORY_OPEN,
    UNTRUSTED_RAG_CLOSE,
    UNTRUSTED_RAG_OPEN,
    UNTRUSTED_TOOL_CLOSE,
    UNTRUSTED_TOOL_OPEN,
    format_isolated_rag_context,
    format_isolated_tool_payload,
    sanitize_external_text,
    sanitize_retrieved_chunks,
    wrap_untrusted_rag_document,
    wrap_untrusted_tool_output,
)
from services.agent.harness.input import (
    InputGuardrailDecision,
    check_input,
    reject_instruction_change,
)
from services.agent.harness.output import OutputGuardrailDecision, check_output
from services.agent.harness.system_prompt import (
    HARNESS_SYSTEM_ADDENDUM,
    SMALL_TALK_REPLY,
    UNTRUSTED_USER_CLOSE,
    UNTRUSTED_USER_OPEN,
    agent_system_prompt,
    wrap_untrusted_user_input,
)
from services.agent.harness.tools import ToolGuardrailDecision, authorize_tool_call

__all__ = [
    "HARNESS_SYSTEM_ADDENDUM",
    "SMALL_TALK_REPLY",
    "UNTRUSTED_MEMORY_CLOSE",
    "UNTRUSTED_MEMORY_OPEN",
    "UNTRUSTED_RAG_CLOSE",
    "UNTRUSTED_RAG_OPEN",
    "UNTRUSTED_TOOL_CLOSE",
    "UNTRUSTED_TOOL_OPEN",
    "UNTRUSTED_USER_CLOSE",
    "UNTRUSTED_USER_OPEN",
    "InputGuardrailDecision",
    "OutputGuardrailDecision",
    "ToolGuardrailDecision",
    "agent_system_prompt",
    "authorize_tool_call",
    "check_input",
    "check_output",
    "format_isolated_rag_context",
    "format_isolated_tool_payload",
    "reject_instruction_change",
    "sanitize_external_text",
    "sanitize_retrieved_chunks",
    "wrap_untrusted_rag_document",
    "wrap_untrusted_tool_output",
    "wrap_untrusted_user_input",
]
