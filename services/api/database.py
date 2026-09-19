"""Compatibility shim — dual-database setup lives in ``services/database.py``."""

from services.database import AUTH_DB_PATH, DATABASE_URL, configure_engine, create_db_and_tables, db, engine, get_auth_db, get_db, get_engine

__all__ = [
    "AUTH_DB_PATH",
    "DATABASE_URL",
    "configure_engine",
    "create_db_and_tables",
    "db",
    "engine",
    "get_auth_db",
    "get_db",
    "get_engine",
]
