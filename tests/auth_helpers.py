"""Shared helpers for Brasaland auth pytest modules (register / login / token)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

users = importlib.import_module("users")
auth = importlib.import_module("auth")

PASSWORD = "secret-password"


def session_identity(client: TestClient, token: str) -> dict:
    """Who the API treats as the signed-in staff member for this token."""
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    identity = response.json()
    # A trusted session always exposes the stored mailbox, not just a token blob.
    assert identity.get("email")
    return identity


def refused_session(response) -> None:
    """No access token was issued (login/register refused a session)."""
    assert response.status_code == 401
    body = response.json()
    assert not body.get("access_token")


def register_session(
    client: TestClient,
    email: str,
    password: str = PASSWORD,
    **extra: object,
) -> dict:
    """POST /auth/register and return the session grant (token + public user)."""
    response = client.post(
        "/auth/register",
        json={"email": email, "password": password, **extra},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload.get("access_token")
    assert payload.get("user", {}).get("email")
    assert "hashed_password" not in payload.get("user", {})
    return payload
