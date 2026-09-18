"""Shared fixtures for Brasaland auth API pytest modules under ``test/``."""

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

from api.app import app  # pylint: disable=wrong-import-position

users = importlib.import_module("users")
auth = importlib.import_module("auth")

PASSWORD = "secret-password"


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    original_database_path = users.DATABASE_PATH
    users.DATABASE_PATH = tmp_path / "company_api.db"
    with TestClient(app) as test_client:
        yield test_client
    users.DATABASE_PATH = original_database_path


def register_user(
    client: TestClient,
    email: str,
    password: str = PASSWORD,
    **extra: object,
) -> dict:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": password, **extra},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert "hashed_password" not in payload.get("user", {})
    return payload
