"""Brasaland agent harness: system prompt + deterministic guardrails."""

from services.agent.harness.input import InputGuardrailDecision, check_input
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
    "UNTRUSTED_USER_CLOSE",
    "UNTRUSTED_USER_OPEN",
    "InputGuardrailDecision",
    "OutputGuardrailDecision",
    "ToolGuardrailDecision",
    "agent_system_prompt",
    "authorize_tool_call",
    "check_input",
    "check_output",
    "wrap_untrusted_user_input",
]
