"""Auditable log of memory-proposal decisions (approve / reject / edit / discard)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.agent.memory.store import DEFAULT_MEMORY_PATH

DEFAULT_AUDIT_PATH = Path(
    os.getenv(
        "AGENT_MEMORY_AUDIT_PATH",
        str(Path(DEFAULT_MEMORY_PATH).with_name("memory_decisions.jsonl")),
    )
)


@dataclass(frozen=True, slots=True)
class MemoryDecisionAudit:
    id: str
    timestamp: str
    outcome: str  # approved | rejected | edited | discarded_topic_change | discarded_ambiguous | proposed
    originating_message: str
    proposal: dict[str, Any]
    intent: str | None = None
    intent_reason: str | None = None
    residual_question: str | None = None
    edited_fact: str | None = None
    thread_id: str | None = None
    detail: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryAuditLog:
    """Append-only JSONL audit trail for memory proposal decisions."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or DEFAULT_AUDIT_PATH)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: MemoryDecisionAudit) -> MemoryDecisionAudit:
        line = json.dumps(entry.as_dict(), ensure_ascii=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return entry

    def list_entries(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-max(0, limit) :]


_AUDIT: MemoryAuditLog | None = None


def get_audit_log(*, path: Path | None = None) -> MemoryAuditLog:
    global _AUDIT
    if path is not None:
        return MemoryAuditLog(path)
    if _AUDIT is None:
        _AUDIT = MemoryAuditLog()
    return _AUDIT


def log_memory_decision(
    *,
    outcome: str,
    originating_message: str,
    proposal: dict[str, Any],
    intent: str | None = None,
    intent_reason: str | None = None,
    residual_question: str | None = None,
    edited_fact: str | None = None,
    thread_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> MemoryDecisionAudit:
    entry = MemoryDecisionAudit(
        id=uuid4().hex,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        outcome=outcome,
        originating_message=originating_message,
        proposal=proposal,
        intent=intent,
        intent_reason=intent_reason,
        residual_question=residual_question,
        edited_fact=edited_fact,
        thread_id=thread_id,
        detail=detail or {},
    )
    return get_audit_log().append(entry)
