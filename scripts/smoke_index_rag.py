#!/usr/bin/env python3
"""Local smoke indexer — populates brasaland_kb without calling the 4Geeks gateway.

Use only when EMBEDDING_API_KEY is unset/placeholder. Production indexing remains:

    uv run python data/process/rag.py

This script monkeypatches ``data.process.rag.embed`` with a deterministic
1024-d vector so Docker Qdrant wiring and chunk counts can be verified offline.
"""

from __future__ import annotations

import hashlib
import math
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from shared.llm_config import EMBEDDING_DIMENSION  # noqa: E402


def _fake_embed(text: str) -> list[float]:
    normalized = text.strip()
    if not normalized:
        raise ValueError("embed() requires non-empty text")
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    values: list[float] = []
    seed = digest
    while len(values) < EMBEDDING_DIMENSION:
        seed = hashlib.sha256(seed).digest()
        for byte in seed:
            values.append((byte / 255.0) * 2.0 - 1.0)
            if len(values) == EMBEDDING_DIMENSION:
                break
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def main() -> int:
    api_key = os.getenv("EMBEDDING_API_KEY", "")
    if api_key and not api_key.startswith("your_") and api_key.startswith("sk-"):
        print(
            "A real EMBEDDING_API_KEY is set. Prefer the production indexer:\n"
            "  uv run python data/process/rag.py"
        )
        return 1

    import data.process.rag as process_rag

    process_rag.embed = _fake_embed  # type: ignore[assignment]
    total = process_rag.setup()
    print(f"Smoke index complete: {total} chunks in '{process_rag.COLLECTION_NAME}'.")
    return 0 if total else 2


if __name__ == "__main__":
    raise SystemExit(main())
