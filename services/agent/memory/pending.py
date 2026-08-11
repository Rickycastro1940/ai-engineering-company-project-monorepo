"""At-most-one pending memory proposal (durable).

A new proposal must not be opened while one is already unresolved.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.agent.memory.store import DEFAULT_MEMORY_PATH

DEFAULT_PENDING_PATH = Path(
    os.getenv(
        "AGENT_MEMORY_PENDING_PATH",
        str(Path(DEFAULT_MEMORY_PATH).with_name("pending_proposal.json")),
    )
)


@dataclass
class PendingProposal:
    id: str
    fact: str
    action: str  # add | change
    why: str | None
    previous_fact: str | None
    kind: str | None
    replace_id: str | None
    originating_message: str
    created_at: str
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingProposal:
        return cls(
            id=str(data.get("id") or uuid4().hex),
            fact=str(data.get("fact") or ""),
            action=str(data.get("action") or "add"),
            why=data.get("why"),
            previous_fact=data.get("previous_fact"),
            kind=data.get("kind"),
            replace_id=data.get("replace_id"),
            originating_message=str(data.get("originating_message") or ""),
            created_at=str(data.get("created_at") or ""),
            thread_id=data.get("thread_id"),
            metadata=dict(data.get("metadata") or {}),
        )


class PendingProposalStore:
    """File-backed singleton pending proposal (max one at a time)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or DEFAULT_PENDING_PATH)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def get(self) -> PendingProposal | None:
        with self._lock:
            if not self.path.is_file():
                return None
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
            if not isinstance(data, dict) or not data.get("fact"):
                return None
            return PendingProposal.from_dict(data)

    def has_pending(self) -> bool:
        return self.get() is not None

    def set(self, pending: PendingProposal) -> PendingProposal:
        """Replace the single pending slot (enforces one-at-a-time)."""
        with self._lock:
            self.path.write_text(
                json.dumps(pending.as_dict(), ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            return pending

    def clear(self) -> PendingProposal | None:
        with self._lock:
            existing = None
            if self.path.is_file():
                try:
                    existing = PendingProposal.from_dict(
                        json.loads(self.path.read_text(encoding="utf-8"))
                    )
                except (json.JSONDecodeError, OSError, TypeError):
                    existing = None
                try:
                    self.path.unlink()
                except OSError:
                    pass
            return existing


_PENDING: PendingProposalStore | None = None


def get_pending_store(*, path: Path | None = None) -> PendingProposalStore:
    global _PENDING
    if path is not None:
        return PendingProposalStore(path)
    if _PENDING is None:
        _PENDING = PendingProposalStore()
    return _PENDING


def new_pending_from_proposal(
    proposal: dict[str, Any],
    *,
    originating_message: str,
    kind: str | None = None,
    replace_id: str | None = None,
    thread_id: str | None = None,
) -> PendingProposal:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return PendingProposal(
        id=uuid4().hex,
        fact=str(proposal.get("fact") or "").strip(),
        action=str(proposal.get("action") or "add"),
        why=proposal.get("why"),
        previous_fact=proposal.get("previous_fact"),
        kind=kind,
        replace_id=replace_id,
        originating_message=originating_message,
        created_at=now,
        thread_id=thread_id,
        metadata={},
    )
