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


def granted_identity(client: TestClient, token: str) -> dict:
    """What /auth/me decides the session is."""
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    return response.json()


def refused_session(response) -> None:
    """The endpoint decided not to issue or continue a staff session."""
    body = response.json()
    assert not body.get("access_token")
    assert response.status_code in {401, 403}


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
    return response.json()
