"""Durable LangGraph checkpointer for Part 3 HITL.

CONTEXT-company.md requires human-in-the-loop pause/resume. LangGraph
``interrupt()`` needs a checkpointer. Use:

- **Postgres** when ``DATABASE_URL`` is PostgreSQL (Supabase / production)
- **SQLite file** for local smoke and pytest (``RFP_ALLOW_SQLITE`` / sqlite URL)
- **MemorySaver only** when ``RFP_CHECKPOINT_MEMORY=1`` (local development)

Never default to an in-memory checkpointer outside local development.
Never use SQLite ``:memory:`` — that is also in-memory.

Checkpointer identity (``thread_id``) is always namespaced by ticket so
concurrent tickets never share a checkpoint::

    RFP-{ticket_id}
    RFP-{ticket_id}:{department_id}   # when a branch is checkpointed alone
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQLITE_PATH = (
    REPO_ROOT / "data" / "process" / "rfp-intake" / "rfp-approval-checkpoints.sqlite"
)

RFP_THREAD_PREFIX = "RFP"
_TICKET_TOKEN = re.compile(r"[^A-Za-z0-9._-]+")

_saver: Any = None
_saver_key: str | None = None
_sqlite_conn: sqlite3.Connection | None = None
_pg_pool: Any = None


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes"}


def allow_memory_checkpointer() -> bool:
    """In-memory checkpointer is opt-in local development only."""
    return _truthy("RFP_CHECKPOINT_MEMORY")


def _clean_thread_token(value: str) -> str:
    cleaned = _TICKET_TOKEN.sub("-", str(value or "").strip())
    cleaned = cleaned.strip("-._")
    if not cleaned:
        raise ValueError("ticket_id is required for checkpoint thread identity")
    return cleaned


def rfp_checkpoint_thread_id(
    ticket_id: str,
    *,
    department_id: str | None = None,
) -> str:
    """Namespace every graph run by ticket (and department when branched).

    Examples:
      - ``RFP-abc123``
      - ``RFP-abc123:marketing``
    """
    ticket = _clean_thread_token(ticket_id)
    # Strip a leading RFP- if callers pass an already-namespaced id as ticket_id.
    if ticket.upper().startswith(f"{RFP_THREAD_PREFIX}-"):
        ticket = ticket[len(RFP_THREAD_PREFIX) + 1 :]
        ticket = _clean_thread_token(ticket)
    base = f"{RFP_THREAD_PREFIX}-{ticket}"
    if department_id:
        dept = _clean_thread_token(department_id)
        return f"{base}:{dept}"
    return base


def approval_thread_id(
    ticket_id: str, *, department_id: str | None = None
) -> str:
    """Stable LangGraph thread for HTTP start-approval + resume."""
    return rfp_checkpoint_thread_id(ticket_id, department_id=department_id)


def ephemeral_rfp_thread_id(ticket_id: str) -> str:
    """One-shot run id still namespaced by ticket (never shared across tickets)."""
    return rfp_checkpoint_thread_id(ticket_id, department_id=f"run-{uuid4().hex}")


def ensure_rfp_thread_id(thread_id: str | None, ticket_id: str) -> str:
    """Force a thread_id under ``RFP-{ticket_id}`` so tickets cannot collide.

    Explicit overrides (tests) are nested as ``RFP-{ticket}:{override}`` unless
    they already start with ``RFP-{ticket}``.
    """
    ticket = _clean_thread_token(ticket_id)
    if ticket.upper().startswith(f"{RFP_THREAD_PREFIX}-"):
        ticket = _clean_thread_token(ticket[len(RFP_THREAD_PREFIX) + 1 :])
    expected = f"{RFP_THREAD_PREFIX}-{ticket}"
    raw = str(thread_id or "").strip()
    if not raw:
        return expected
    if raw == expected or raw.startswith(f"{expected}:"):
        return raw
    # Already RFP- namespaced for a *different* ticket — still nest under ours.
    if raw.upper().startswith(f"{RFP_THREAD_PREFIX}-"):
        return f"{expected}:{_clean_thread_token(raw)}"
    return f"{expected}:{_clean_thread_token(raw)}"


def _sqlalchemy_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip()


def _is_postgres_url(url: str) -> bool:
    scheme = urlparse(url).scheme.lower()
    return scheme.startswith("postgres")


def _is_sqlite_url(url: str) -> bool:
    scheme = urlparse(url).scheme.lower()
    return scheme.startswith("sqlite")


def postgres_conninfo(url: str) -> str:
    """Strip SQLAlchemy dialects so psycopg can connect."""
    cleaned = url.strip()
    for prefix in (
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
        "postgresql+asyncpg://",
        "postgres+psycopg2://",
        "postgres+psycopg://",
    ):
        if cleaned.lower().startswith(prefix):
            rest = cleaned.split("://", 1)[1]
            return f"postgresql://{rest}"
    if cleaned.lower().startswith("postgres://"):
        return "postgresql://" + cleaned.split("://", 1)[1]
    return cleaned


def sqlite_checkpoint_path(database_url: str | None = None) -> Path:
    """File-backed SQLite path (never ``:memory:``)."""
    explicit = (os.getenv("RFP_CHECKPOINT_SQLITE") or "").strip()
    if explicit and explicit not in {":memory:", "file:memory"}:
        path = Path(explicit)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    url = database_url if database_url is not None else _sqlalchemy_url()
    if url and _is_sqlite_url(url):
        raw = url.split(":///", 1)[-1] if ":///" in url else url.split("://", 1)[-1]
        if raw and raw not in {":memory:", "memory"}:
            db_path = Path(raw)
            sibling = db_path.with_name(
                db_path.stem + ".langgraph-checkpoints.sqlite"
            )
            sibling.parent.mkdir(parents=True, exist_ok=True)
            return sibling
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DEFAULT_SQLITE_PATH


def checkpoint_backend() -> str:
    """Return ``postgres``, ``sqlite``, or ``memory`` (local opt-in only)."""
    if allow_memory_checkpointer():
        return "memory"
    url = _sqlalchemy_url()
    if url and _is_postgres_url(url):
        return "postgres"
    if url and _is_sqlite_url(url):
        return "sqlite"
    if _truthy("RFP_ALLOW_SQLITE") or os.getenv("PYTEST_CURRENT_TEST"):
        return "sqlite"
    if url:
        # Unknown URL scheme — do not silently fall back to MemorySaver.
        raise RuntimeError(
            f"Unsupported DATABASE_URL scheme for Part 3 checkpointer: {url!r}. "
            "Use PostgreSQL (production) or sqlite:///… / RFP_ALLOW_SQLITE=1 (local)."
        )
    # Local default: sqlite file, never in-memory.
    return "sqlite"


def _open_sqlite_saver(path: Path) -> Any:
    global _sqlite_conn
    from langgraph.checkpoint.sqlite import SqliteSaver

    path.parent.mkdir(parents=True, exist_ok=True)
    _sqlite_conn = sqlite3.connect(str(path), check_same_thread=False)
    saver = SqliteSaver(_sqlite_conn)
    saver.setup()
    return saver


def _open_postgres_saver(url: str) -> Any:
    global _pg_pool
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    conninfo = postgres_conninfo(url)
    _pg_pool = ConnectionPool(
        conninfo=conninfo,
        min_size=1,
        max_size=4,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        open=True,
    )
    saver = PostgresSaver(_pg_pool)
    saver.setup()
    return saver


def get_approval_checkpointer() -> Any:
    """Return the process checkpointer for the Part 3 graph (durable by default)."""
    global _saver, _saver_key
    backend = checkpoint_backend()
    if backend == "postgres":
        key = f"postgres:{postgres_conninfo(_sqlalchemy_url())}"
    elif backend == "sqlite":
        key = f"sqlite:{sqlite_checkpoint_path()}"
    else:
        key = "memory"
    if _saver is not None and _saver_key == key:
        return _saver

    reset_approval_checkpointer()
    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        _saver = MemorySaver()
        _saver_key = key
        return _saver
    if backend == "postgres":
        _saver = _open_postgres_saver(_sqlalchemy_url())
        _saver_key = key
        return _saver
    path = sqlite_checkpoint_path()
    if str(path) in {":memory:", "file::memory:"}:
        raise RuntimeError("Refusing in-memory SQLite checkpointer; use a file path")
    _saver = _open_sqlite_saver(path)
    _saver_key = key
    return _saver


def reset_approval_checkpointer() -> None:
    """Drop the cached saver (call when DATABASE_URL changes, e.g. pytest)."""
    global _saver, _saver_key, _sqlite_conn, _pg_pool
    if _sqlite_conn is not None:
        try:
            _sqlite_conn.close()
        except Exception:
            pass
        _sqlite_conn = None
    if _pg_pool is not None:
        try:
            _pg_pool.close()
        except Exception:
            pass
        _pg_pool = None
    _saver = None
    _saver_key = None
    try:
        from data.pipelines.rfp_approval import graph as approval_graph

        approval_graph._COMPILED = None
        approval_graph._COMPILED_INTERRUPT = None
        approval_graph._COMPILED_KEY = None
    except Exception:
        pass


def checkpointer_kind(saver: Any | None = None) -> str:
    obj = saver if saver is not None else _saver
    name = type(obj).__name__ if obj is not None else ""
    if name in {"MemorySaver", "InMemorySaver"}:
        return "memory"
    if "Postgres" in name:
        return "postgres"
    if "Sqlite" in name:
        return "sqlite"
    return name or "unknown"
