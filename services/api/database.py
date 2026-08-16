"""Shared DB layer — SQLModel for relational data; TinyDB only for legacy auth.

RFP Ticket / metadata / DepartmentSection.key_aspects MUST use SQLModel
(PostgreSQL via DATABASE_URL / Supabase). TinyDB is never the source of truth
for RFP entities.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]

# Legacy auth store only — not used for RFP Ticket / DepartmentSection.
try:
    from tinydb import TinyDB

    db = TinyDB(str(REPO_ROOT / "data" / "auth.json"))
except ImportError:  # pragma: no cover — TinyDB optional; never required for RFP
    db = None

_engine = None
_engine_url: str | None = None


def database_url() -> str:
    """Resolve SQLModel URL. Prefer Postgres (Supabase) via DATABASE_URL."""
    env = (os.getenv("DATABASE_URL") or "").strip()
    if env:
        return env
    allow_sqlite = (os.getenv("RFP_ALLOW_SQLITE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    # Pytest sets PYTEST_CURRENT_TEST — allow ephemeral sqlite in tests only.
    in_pytest = bool(os.getenv("PYTEST_CURRENT_TEST"))
    if allow_sqlite or in_pytest:
        path = REPO_ROOT / "data" / "process" / "rfp-intake" / "rfp.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    raise RuntimeError(
        "DATABASE_URL is required for RFP persistence (PostgreSQL / Supabase). "
        "Set DATABASE_URL=postgresql+psycopg://… or export RFP_ALLOW_SQLITE=1 for local smoke only."
    )


def get_engine():
    global _engine, _engine_url
    url = database_url()
    if _engine is None or _engine_url != url:
        kwargs: dict = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        _engine_url = url
    return _engine


def reset_engine() -> None:
    global _engine, _engine_url
    _engine = None
    _engine_url = None
    try:
        from data.pipelines.rfp_approval.checkpointer import reset_approval_checkpointer

        reset_approval_checkpointer()
    except Exception:
        pass


def get_db() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def create_db_and_tables(*_table_models: type[SQLModel]) -> None:
    """Create all registered SQLModel tables on the configured engine."""
    # Import RFP models so their tables register on SQLModel.metadata.
    from services.rfp import models as _rfp_models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


# Back-compat: some modules may still reference ``engine`` — use get_engine().
engine = None  # type: ignore[assignment]
