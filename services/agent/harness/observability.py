"""Minimal observability for guardrail blocks and redirects.

Every block / redirect is classified as ``structural``, ``content``, or
``security`` and written to the JSONL audit. A session summary (counts per
guardrail and failure type) is available via:

- ``GET /agent/guardrails/summary``
- ``uv run python -m services.agent.harness.observability``
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any
from uuid import uuid4

from services.agent.harness.restrictions import (
    ACTION_BLOCK,
    ACTION_REDIRECT,
    FAILURE_CONTENT,
    FAILURE_SECURITY,
    FAILURE_STRUCTURAL,
    REASON_ALLERGEN_ABSOLUTE_SAFETY,
    REASON_BAD_OUTPUT_FORMAT,
    REASON_CASUAL_REDIRECT,
    REASON_CASUAL_STEER,
    REASON_CURRENCY_CONVERSION,
    REASON_EXTERNAL_INJECTION,
    REASON_JAILBREAK,
    REASON_OFF_TOPIC,
    REASON_PERSONAL_USE,
    REASON_RAG_INTERNALS,
    REASON_SENSITIVE_CONTEXT_LEAK,
    REASON_SMALL_TALK_REDIRECT,
    REASON_SYSTEM_PROMPT_LEAK,
    REASON_TOOL_WRITE_DENIED,
)

_SECURITY_REASONS = frozenset(
    {
        REASON_JAILBREAK,
        REASON_SYSTEM_PROMPT_LEAK,
        REASON_SENSITIVE_CONTEXT_LEAK,
        REASON_RAG_INTERNALS,
        REASON_EXTERNAL_INJECTION,
        REASON_TOOL_WRITE_DENIED,
    }
)
_STRUCTURAL_REASONS = frozenset({REASON_BAD_OUTPUT_FORMAT})
_CONTENT_REASONS = frozenset(
    {
        REASON_OFF_TOPIC,
        REASON_PERSONAL_USE,
        REASON_CURRENCY_CONVERSION,
        REASON_ALLERGEN_ABSOLUTE_SAFETY,
        REASON_CASUAL_STEER,
        REASON_CASUAL_REDIRECT,
        REASON_SMALL_TALK_REDIRECT,
    }
)

_SESSION_ID: str | None = None


def classify_failure_type(reason: str | None) -> str:
    """Map a guardrail reason to structural / content / security."""
    key = reason or ""
    if key in _SECURITY_REASONS:
        return FAILURE_SECURITY
    if key in _STRUCTURAL_REASONS:
        return FAILURE_STRUCTURAL
    if key in _CONTENT_REASONS:
        return FAILURE_CONTENT
    # Unknown reasons still count — default to content (scope/policy).
    return FAILURE_CONTENT


def current_session_id() -> str:
    """Return the active test-session id (created on first use)."""
    global _SESSION_ID
    if not _SESSION_ID:
        _SESSION_ID = uuid4().hex
    return _SESSION_ID


def start_guardrail_session() -> str:
    """Start a new observability session (e.g. beginning of a test run)."""
    global _SESSION_ID
    _SESSION_ID = uuid4().hex
    return _SESSION_ID


def summarize_events(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Count blocks/redirects by guardrail, failure type, reason, and action."""
    triggered = [
        row
        for row in entries
        if (row.get("action") or row.get("outcome")) in {ACTION_BLOCK, ACTION_REDIRECT, "redact"}
    ]
    by_type: Counter[str] = Counter()
    by_guardrail: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    for row in triggered:
        failure = row.get("failure_type") or classify_failure_type(row.get("reason"))
        by_type[failure] += 1
        by_guardrail[str(row.get("guardrail") or row.get("layer") or "unknown")] += 1
        by_reason[str(row.get("reason") or "unknown")] += 1
        action = row.get("action")
        if action not in {ACTION_BLOCK, ACTION_REDIRECT}:
            action = ACTION_REDIRECT if row.get("outcome") == "redact" else ACTION_BLOCK
        by_action[str(action)] += 1
    return {
        "session_id": current_session_id(),
        "triggered": len(triggered),
        "by_failure_type": {
            FAILURE_STRUCTURAL: by_type.get(FAILURE_STRUCTURAL, 0),
            FAILURE_CONTENT: by_type.get(FAILURE_CONTENT, 0),
            FAILURE_SECURITY: by_type.get(FAILURE_SECURITY, 0),
        },
        "by_guardrail": dict(sorted(by_guardrail.items())),
        "by_reason": dict(sorted(by_reason.items())),
        "by_action": {
            ACTION_BLOCK: by_action.get(ACTION_BLOCK, 0),
            ACTION_REDIRECT: by_action.get(ACTION_REDIRECT, 0),
        },
    }


def session_summary(*, session_id: str | None = None) -> dict[str, Any]:
    """Load the audit log and summarize the current (or given) session."""
    from services.agent.harness.audit import get_guardrail_audit

    sid = session_id or current_session_id()
    entries = get_guardrail_audit().list_entries(limit=100_000, session_id=sid)
    summary = summarize_events(entries)
    summary["session_id"] = sid
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Summarize Brasaland guardrail blocks/redirects for this session."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Start a new session id (later events are counted separately).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Summarize the entire JSONL file, not only the current session.",
    )
    args = parser.parse_args(argv)
    if args.reset:
        start_guardrail_session()
        print(json.dumps({"session_id": current_session_id(), "reset": True}, indent=2))
        return 0
    if args.all:
        from services.agent.harness.audit import get_guardrail_audit

        payload = summarize_events(get_guardrail_audit().list_entries(limit=100_000))
        payload["session_id"] = "all"
    else:
        payload = session_summary()
    print(json.dumps(payload, indent=2))
    return 0
