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
from services import database as dual_db  # pylint: disable=wrong-import-position

users = importlib.import_module("users")
auth = importlib.import_module("auth")

PASSWORD = "secret-password"


def granted_identity(client: TestClient, token: str) -> dict:
    """Who the API treats as the current staff member for this session."""
    identity = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    # A trusted session always exposes the stored mailbox, not just a token blob.
    assert identity.get("email")
    return identity


def refused_session(response) -> None:
    """No new session token, and no kitchen stock list (anonymous inventory)."""
    body = response.json()
    assert not body.get("access_token")
    assert not isinstance(body, list)


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    original_database_path = users.DATABASE_PATH
    users.DATABASE_PATH = tmp_path / "auth.json"
    original_auth_path = dual_db.AUTH_DB_PATH
    dual_db.AUTH_DB_PATH = users.DATABASE_PATH
    original_url = dual_db.DATABASE_URL
    dual_db.configure_engine(f"sqlite:///{tmp_path / 'inventory.sqlite'}")
    with TestClient(app) as test_client:
        yield test_client
    users.DATABASE_PATH = original_database_path
    dual_db.AUTH_DB_PATH = original_auth_path
    dual_db.configure_engine(original_url)


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
    payload = response.json()
    # Registration is a session grant: a token plus the created staff row.
    assert payload.get("access_token")
    assert payload.get("user", {}).get("email")
    assert "hashed_password" not in payload.get("user", {})
    return payload
