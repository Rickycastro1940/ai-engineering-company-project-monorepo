"""Append-only JSONL audit of harness / guardrail blocks and redirects."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.agent.harness.observability import classify_failure_type, current_session_id
from services.agent.harness.restrictions import ACTION_BLOCK, ACTION_REDIRECT

logger = logging.getLogger("brasaland.guardrails")

DEFAULT_AUDIT_PATH = Path(
    os.getenv(
        "AGENT_GUARDRAIL_AUDIT_PATH",
        str(
            Path(__file__).resolve().parents[3]
            / "data"
            / "process"
            / "agent-guardrails"
            / "guardrail_decisions.jsonl"
        ),
    )
)


@dataclass(frozen=True, slots=True)
class GuardrailAudit:
    id: str
    timestamp: str
    session_id: str
    layer: str
    guardrail: str
    action: str
    failure_type: str
    outcome: str
    reason: str | None
    question: str
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class GuardrailAuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or DEFAULT_AUDIT_PATH)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: GuardrailAudit) -> GuardrailAudit:
        line = json.dumps(entry.as_dict(), ensure_ascii=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return entry

    def list_entries(
        self, *, limit: int = 100, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if session_id and row.get("session_id") != session_id:
                    continue
                rows.append(row)
        return rows[-max(0, limit) :]


_AUDIT: GuardrailAuditLog | None = None


def get_guardrail_audit(*, path: Path | None = None) -> GuardrailAuditLog:
    global _AUDIT
    if path is not None:
        return GuardrailAuditLog(path)
    if _AUDIT is None:
        _AUDIT = GuardrailAuditLog()
    return _AUDIT


def log_guardrail_decision(
    *,
    layer: str,
    outcome: str,
    reason: str | None,
    question: str,
    detail: dict[str, Any] | None = None,
    action: str | None = None,
    guardrail: str | None = None,
) -> GuardrailAudit | None:
    """Persist a block or redirect. Allows are not logged (minimal observability)."""
    resolved_action = action
    if resolved_action is None:
        if outcome in {ACTION_BLOCK, "blocked"}:
            resolved_action = ACTION_BLOCK
        elif outcome in {ACTION_REDIRECT, "redact"}:
            resolved_action = ACTION_REDIRECT
        else:
            return None
    if resolved_action not in {ACTION_BLOCK, ACTION_REDIRECT}:
        return None

    failure_type = classify_failure_type(reason)
    gate = guardrail or layer
    entry = GuardrailAudit(
        id=uuid4().hex,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        session_id=current_session_id(),
        layer=layer,
        guardrail=gate,
        action=resolved_action,
        failure_type=failure_type,
        outcome=outcome,
        reason=reason,
        question=question,
        detail=detail or {},
    )
    logger.info(
        "guardrail %s failure_type=%s guardrail=%s reason=%s",
        resolved_action,
        failure_type,
        gate,
        reason,
    )
    return get_guardrail_audit().append(entry)
