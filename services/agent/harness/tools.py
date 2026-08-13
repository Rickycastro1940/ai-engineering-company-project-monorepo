"""Tool / action guardrails — least privilege around MCP and inventory tools.

The compiled graph only exposes read paths. This module is the harness gate
so a steered model (or a future write-capable tool) cannot bypass that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.agent.harness.restrictions import (
    REASON_TOOL_WRITE_DENIED,
    TOOL_WRITE_REFUSAL,
    inventory_write_attempt,
)

ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "lookup_ticket",
        "lookup_inventory",
        "retrieve",
        "recall_memory",
        "write_memory",
        "manage_incident_ticket",  # MCP tool; agent uses read actions only
        "query_inventory",
    }
)


@dataclass(frozen=True, slots=True)
class ToolGuardrailDecision:
    allowed: bool
    reason: str | None
    refusal: str | None
    tool: str
    layer: str = "tool"

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "refusal": self.refusal,
            "tool": self.tool,
            "layer": self.layer,
        }


def authorize_tool_call(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> ToolGuardrailDecision:
    """Deny inventory writes; allow the existing read-only tool set."""
    name = (tool_name or "").strip()
    args = arguments or {}

    if inventory_write_attempt(name, args) or _explicit_inventory_write(name, args):
        return ToolGuardrailDecision(
            allowed=False,
            reason=REASON_TOOL_WRITE_DENIED,
            refusal=TOOL_WRITE_REFUSAL,
            tool=name,
        )
    return ToolGuardrailDecision(
        allowed=True,
        reason=None,
        refusal=None,
        tool=name,
    )


def _explicit_inventory_write(tool_name: str, arguments: dict[str, Any]) -> bool:
    name = tool_name.casefold()
    action = str(arguments.get("action") or "").casefold()
    if "inventory" in name and action in {
        "create",
        "update",
        "delete",
        "write",
        "upsert",
        "patch",
    }:
        return True
    if arguments.get("write") in (True, "true", "1", 1):
        return "inventory" in name
    return False
