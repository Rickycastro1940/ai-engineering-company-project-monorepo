"""Pytest fixtures for Brasaland auth endpoint modules under ``tests/``."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.app import app  # noqa: E402  pylint: disable=wrong-import-position

users = importlib.import_module("users")


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Isolate the staff user store so each test starts with an empty roster."""
    original_database_path = users.DATABASE_PATH
    users.DATABASE_PATH = tmp_path / "company_api.db"
    with TestClient(app) as test_client:
        yield test_client
    users.DATABASE_PATH = original_database_path
