"""Dual database connections: TinyDB (auth) + SQLModel engine (inventory)."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine
from tinydb import TinyDB

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env", override=True)

DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# TinyDB: users and profiles only. Never replicate users in SQLModel/Supabase.
AUTH_DB_PATH = Path(os.getenv("AUTH_DB_PATH", DATA_DIR / "auth.json"))
AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

db: TinyDB | None = None
_auth_db_path: Path | None = None


def get_auth_db() -> TinyDB:
    """Return the TinyDB client used for auth (users/profiles)."""
    global db, _auth_db_path
    path = Path(AUTH_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    if db is None or _auth_db_path != path:
        if db is not None:
            db.close()
        db = TinyDB(path)
        _auth_db_path = path
    return db

_DEFAULT_SQLITE_URL = f"sqlite:///{DATA_DIR / 'inventory.sqlite'}"


_PLACEHOLDER_MARKERS = ("YOUR_DATABASE_PASSWORD", "PASTE_PASSWORD_HERE")


def _env_database_url() -> str:
    url = os.getenv("DATABASE_URL", _DEFAULT_SQLITE_URL).strip()
    if not url or any(marker in url for marker in _PLACEHOLDER_MARKERS):
        return _DEFAULT_SQLITE_URL
    return url


DATABASE_URL = _env_database_url()
engine: Engine | None = None


def _sqlalchemy_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


def _build_engine(url: str) -> Engine:
    url = _sqlalchemy_url(url)
    engine_kwargs: dict = {"echo": False}
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_pre_ping"] = True
        if "pooler.supabase.com" in url:
            # Transaction pooler (6543) with psycopg2 can fail with
            # "server didn't return client encoding". Session pooler (5432)
            # on the same host is the compatible SQLAlchemy path.
            if ":6543/" in url:
                url = url.replace(":6543/", ":5432/")
            engine_kwargs["poolclass"] = NullPool
            engine_kwargs["connect_args"] = {
                "sslmode": "require",
                "client_encoding": "utf8",
            }
    return create_engine(url, **engine_kwargs)


def configure_engine(url: str | None = None) -> Engine:
    global DATABASE_URL, engine
    DATABASE_URL = url or _env_database_url()
    engine = _build_engine(DATABASE_URL)
    return engine


def get_engine() -> Engine:
    global engine
    if engine is None:
        return configure_engine(DATABASE_URL)
    return engine


def get_db() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


def create_db_and_tables() -> None:
    """Create Ingredient / IngredientEntry / IngredientExit tables (idempotent)."""
    from services.models import Ingredient, IngredientEntry, IngredientExit  # noqa: F401

    global engine
    if engine is None:
        configure_engine()
    SQLModel.metadata.create_all(engine)


configure_engine()
get_auth_db()
