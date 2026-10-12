"""POST /auth/token + JWT helpers — session token decisions.

Happy / edge / failure cases for AUTH-088 (Building Bullet-Proof Applications).
Covers the CTO regression: expired tokens must be rejected, not silently accepted.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt

from tests.auth_helpers import (
    PASSWORD,
    auth,
    refused_session,
    register_session,
    session_identity,
    users,
)


def test_token_form_login_identifies_that_account(client) -> None:
    """Happy: OAuth2 form login returns a token that resolves to the same staff row."""
    registered = register_session(client, "nicolas.park@brasaland.test")

    response = client.post(
        "/auth/token",
        data={"username": "nicolas.park@brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    # Business rule: JWT subject is the user id, not the email string.
    assert auth.decode_access_token(token) == str(registered["user"]["id"])
    identity = session_identity(client, token)
    assert identity["id"] == registered["user"]["id"]
    assert identity["email"] == "nicolas.park@brasaland.test"


def test_token_accepts_mixed_case_username(client) -> None:
    """Edge: form username is matched case-insensitively like JSON login."""
    register_session(client, "lucia.fernandez@brasaland.test")

    response = client.post(
        "/auth/token",
        data={"username": "Lucia.Fernandez@Brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    identity = session_identity(client, response.json()["access_token"])
    assert identity["email"] == "lucia.fernandez@brasaland.test"


def test_token_rejects_wrong_password(client) -> None:
    """Failure: wrong password does not mint a token."""
    register_session(client, "ops@brasaland.test")

    response = client.post(
        "/auth/token",
        data={"username": "ops@brasaland.test", "password": "wrong-password"},
    )

    refused_session(response)


def test_token_rejects_expired_jwt(client) -> None:
    """Failure: an expired JWT cannot open a staff session (AUTH-088 regression)."""
    registered = register_session(client, "ops@brasaland.test")
    expired = jwt.encode(
        {
            "sub": str(registered["user"]["id"]),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        auth.SECRET_KEY,
        algorithm=auth.ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.decode_access_token(expired)
    assert exc_info.value.status_code == 401

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json().get("email") is None


def test_token_rejects_jwt_signed_with_wrong_secret(client) -> None:
    """Failure: a token minted with a different secret is not a valid session."""
    registered = register_session(client, "ops@brasaland.test")
    forged = jwt.encode(
        {
            "sub": str(registered["user"]["id"]),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        "not-the-brasaland-secret",
        algorithm=auth.ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.decode_access_token(forged)
    assert exc_info.value.status_code == 401


def test_token_rejects_inactive_staff_on_form_login(client) -> None:
    """Failure: deactivated staff cannot obtain a form token either."""
    registered = register_session(client, "ops@brasaland.test")
    users.update_user(registered["user"]["id"], is_active=False)

    response = client.post(
        "/auth/token",
        data={"username": "ops@brasaland.test", "password": PASSWORD},
    )

    refused_session(response)
