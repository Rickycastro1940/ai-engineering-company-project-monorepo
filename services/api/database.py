from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from tinydb import TinyDB

DEFAULT_DB_PATH = Path(__file__).with_name("suppliers_db.json")


def db_path() -> Path:
    configured_path = os.environ.get("SUPPLIERS_DB_PATH")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_DB_PATH


def model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return json.loads(model.json())


def supplier_table():
    target_path = db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    db = TinyDB(target_path)
    return db, db.table("suppliers")
