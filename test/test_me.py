"""GET /auth/me — current staff identity from a Bearer JWT."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import jwt

from test.conftest import auth, register_user, users


def test_me_happy_path_returns_profile_for_valid_token(client) -> None:
    registered = register_user(
        client,
        "jake.morrison@brasaland.test",
        name="Jake Morrison",
        phone="+1 305 000 0000",
        address="Miami training",
    )

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "jake.morrison@brasaland.test"
    assert body["name"] == "Jake Morrison"
    assert "hashed_password" not in body


def test_me_edge_subject_is_numeric_user_id(client) -> None:
    registered = register_user(client, "ops@brasaland.test")
    user_id = registered["user"]["id"]
    payload = jwt.decode(
        registered["access_token"],
        auth.SECRET_KEY,
        algorithms=[auth.ALGORITHM],
    )

    assert payload["sub"] == str(user_id)
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == user_id


def test_me_failure_expired_malformed_wrong_secret_and_inactive(client) -> None:
    registered = register_user(client, "ops@brasaland.test")
    user_id = str(registered["user"]["id"])

    expired = jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        auth.SECRET_KEY,
        algorithm=auth.ALGORITHM,
    )
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

    malformed = client.get("/auth/me", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert malformed.status_code == 401

    wrong_secret = jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        "not-the-brasaland-secret",
        algorithm=auth.ALGORITHM,
    )
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {wrong_secret}"}).status_code == 401

    non_numeric = jwt.encode(
        {"sub": "not-an-id", "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        auth.SECRET_KEY,
        algorithm=auth.ALGORITHM,
    )
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {non_numeric}"}).status_code == 401

    users.update_user(registered["user"]["id"], is_active=False)
    still_active_token = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {registered['access_token']}"},
    )
    assert still_active_token.status_code == 401
