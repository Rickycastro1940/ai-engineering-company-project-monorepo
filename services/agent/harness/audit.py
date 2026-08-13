"""Append-only JSONL audit of harness / guardrail decisions."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

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
    layer: str
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
) -> GuardrailAudit:
    entry = GuardrailAudit(
        id=uuid4().hex,
        timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        layer=layer,
        outcome=outcome,
        reason=reason,
        question=question,
        detail=detail or {},
    )
    return get_guardrail_audit().append(entry)
