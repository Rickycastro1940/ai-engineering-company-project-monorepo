"""JSON-file semantic memory store (durable across agent runs)."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MEMORY_PATH = REPO_ROOT / "data" / "process" / "agent-memory" / "semantic.json"


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
    """Simple append/upsert store — company semantic facts only."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or os.getenv("AGENT_MEMORY_PATH") or DEFAULT_MEMORY_PATH)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"records": []})

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"records": []}

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def list_records(self) -> list[MemoryRecord]:
        raw = self._read().get("records") or []
        out: list[MemoryRecord] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            out.append(
                MemoryRecord(
                    id=str(item.get("id") or ""),
                    kind=str(item.get("kind") or ""),
                    text=str(item.get("text") or ""),
                    source=str(item.get("source") or ""),
                    created_at=str(item.get("created_at") or ""),
                    updated_at=str(item.get("updated_at") or ""),
                    metadata=dict(item.get("metadata") or {}),
                )
            )
        return out

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
        with self._lock:
            data = self._read()
            records = list(data.get("records") or [])
            for item in records:
                if not isinstance(item, dict):
                    continue
                if (
                    str(item.get("kind")) == kind
                    and " ".join(str(item.get("text") or "").split()).casefold()
                    == normalized.casefold()
                ):
                    item["updated_at"] = now
                    item["source"] = source
                    item["metadata"] = dict(metadata or item.get("metadata") or {})
                    self._write({"records": records})
                    return MemoryRecord(
                        id=str(item["id"]),
                        kind=kind,
                        text=str(item["text"]),
                        source=source,
                        created_at=str(item.get("created_at") or now),
                        updated_at=now,
                        metadata=dict(item.get("metadata") or {}),
                    )

            record = MemoryRecord(
                id=uuid4().hex,
                kind=kind,
                text=normalized,
                source=source,
                created_at=now,
                updated_at=now,
                metadata=dict(metadata or {}),
            )
            records.append(record.as_dict())
            self._write({"records": records})
            return record

    def search(self, query: str, *, limit: int = 5) -> list[MemoryRecord]:
        """Keyword overlap retrieval (deterministic, no embeddings required)."""
        tokens = {t for t in re.findall(r"[a-z0-9áéíóúñü+#.-]+", (query or "").casefold()) if len(t) > 2}
        if not tokens:
            return []
        scored: list[tuple[int, MemoryRecord]] = []
        for record in self.list_records():
            hay = f"{record.kind} {record.text}".casefold()
            score = sum(1 for t in tokens if t in hay)
            if score:
                scored.append((score, record))
        scored.sort(key=lambda pair: (-pair[0], pair[1].updated_at), reverse=False)
        scored.sort(key=lambda pair: (-pair[0], pair[1].updated_at))
        return [rec for _, rec in scored[: max(0, limit)]]

    def clear(self) -> None:
        with self._lock:
            self._write({"records": []})


_STORE: MemoryStore | None = None


def get_memory_store(path: Path | None = None) -> MemoryStore:
    global _STORE
    if path is not None:
        return MemoryStore(path)
    if _STORE is None:
        _STORE = MemoryStore()
    return _STORE
