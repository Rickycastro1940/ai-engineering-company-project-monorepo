"""SQLite semantic memory store (durable key/document backend).

Chosen as the Brasaland semantic-memory backend — see
``docs/agent/MEMORY_BACKEND.md``. Episodic history stays in agent traces.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEMORY_PATH = REPO_ROOT / "data" / "process" / "agent-memory" / "semantic.sqlite"


@dataclass
class MemoryRecord:
    id: str
    kind: str
    text: str
    source: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryStore:
    """Persistent semantic facts for Brasaland ops/commercial memory."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or os.getenv("AGENT_MEMORY_PATH") or DEFAULT_MEMORY_PATH)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS semantic_memory (
                        id TEXT PRIMARY KEY,
                        kind TEXT NOT NULL,
                        text TEXT NOT NULL,
                        text_norm TEXT NOT NULL,
                        source TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_semantic_kind_text
                    ON semantic_memory (kind, text_norm)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_semantic_kind
                    ON semantic_memory (kind)
                    """
                )
                conn.commit()

    def list_records(self) -> list[MemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, kind, text, source, created_at, updated_at, metadata_json
                FROM semantic_memory
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def upsert(
        self,
        *,
        text: str,
        kind: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        normalized = " ".join(text.split())
        text_norm = normalized.casefold()
        meta = dict(metadata or {})
        meta_json = json.dumps(meta, ensure_ascii=True, default=str)

        with self._lock:
            with self._connect() as conn:
                existing = conn.execute(
                    """
                    SELECT id, created_at FROM semantic_memory
                    WHERE kind = ? AND text_norm = ?
                    """,
                    (kind, text_norm),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE semantic_memory
                        SET text = ?, source = ?, updated_at = ?, metadata_json = ?
                        WHERE id = ?
                        """,
                        (normalized, source, now, meta_json, existing["id"]),
                    )
                    conn.commit()
                    return MemoryRecord(
                        id=str(existing["id"]),
                        kind=kind,
                        text=normalized,
                        source=source,
                        created_at=str(existing["created_at"]),
                        updated_at=now,
                        metadata=meta,
                    )

                record_id = uuid4().hex
                conn.execute(
                    """
                    INSERT INTO semantic_memory
                    (id, kind, text, text_norm, source, created_at, updated_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (record_id, kind, normalized, text_norm, source, now, now, meta_json),
                )
                conn.commit()
                return MemoryRecord(
                    id=record_id,
                    kind=kind,
                    text=normalized,
                    source=source,
                    created_at=now,
                    updated_at=now,
                    metadata=meta,
                )

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        """Keyword overlap retrieval over structured semantic facts."""
        tokens = {
            t
            for t in re.findall(r"[a-z0-9áéíóúñü+#.-]+", (query or "").casefold())
            if len(t) > 2
        }
        if not tokens:
            return []

        records = self.list_records()
        scored: list[tuple[int, MemoryRecord]] = []
        for record in records:
            hay = f"{record.kind} {record.text}".casefold()
            score = sum(1 for t in tokens if t in hay)
            if score:
                scored.append((score, record))
        scored.sort(key=lambda pair: (-pair[0], pair[1].updated_at))
        return [rec for _, rec in scored[: max(0, limit)]]

    def clear(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM semantic_memory")
                conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return MemoryRecord(
            id=str(row["id"]),
            kind=str(row["kind"]),
            text=str(row["text"]),
            source=str(row["source"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            metadata=metadata,
        )


_STORE: MemoryStore | None = None


def get_memory_store(path: Path | None = None) -> MemoryStore:
    global _STORE
    if path is not None:
        return MemoryStore(path)
    if _STORE is None:
        _STORE = MemoryStore()
    return _STORE
