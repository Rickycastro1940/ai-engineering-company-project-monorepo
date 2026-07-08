from __future__ import annotations

import os
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

default_db_path = DATA_DIR / "inventory.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{default_db_path}")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def get_db():
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
