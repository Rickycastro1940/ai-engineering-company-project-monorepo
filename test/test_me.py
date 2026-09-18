"""GET /auth/me — session identity and when a token is no longer trusted."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import jwt

from test.conftest import auth, granted_identity, register_user, refused_session, users


def test_me_returns_the_staff_record_bound_to_the_session(client) -> None:
    registered = register_user(
        client,
        "jake.morrison@brasaland.test",
        name="Jake Morrison",
        phone="+1 305 000 0000",
        address="Miami training",
    )
    identity = granted_identity(client, registered["access_token"])
    stored = users.get_user_by_id(identity["id"])
    assert identity["email"] == "jake.morrison@brasaland.test"
    assert identity["name"] == stored["name"] == "Jake Morrison"
    assert identity["phone"] == stored["phone"]
    assert identity["address"] == stored["address"]


def test_me_session_subject_is_the_user_id(client) -> None:
    registered = register_user(client, "ops@brasaland.test")
    identity = granted_identity(client, registered["access_token"])
    subject = jwt.decode(
        registered["access_token"],
        auth.SECRET_KEY,
        algorithms=[auth.ALGORITHM],
    )["sub"]
    assert str(identity["id"]) == subject
    assert users.get_user_by_id(int(subject))["email"] == "ops@brasaland.test"


def test_me_rejects_expired_forged_or_inactive_sessions(client) -> None:
    registered = register_user(client, "ops@brasaland.test")
    user_id = str(registered["user"]["id"])

    expired = jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        auth.SECRET_KEY,
        algorithm=auth.ALGORITHM,
    )
    forged = jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        "not-the-brasaland-secret",
        algorithm=auth.ALGORITHM,
    )
    garbage = "not-a-valid-jwt"
    non_user = jwt.encode(
        {"sub": "not-an-id", "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        auth.SECRET_KEY,
        algorithm=auth.ALGORITHM,
    )

    for token in (expired, forged, garbage, non_user):
        refused_session(client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}))

    users.update_user(registered["user"]["id"], is_active=False)
    refused_session(
        client.get("/auth/me", headers={"Authorization": f"Bearer {registered['access_token']}"})
    )
    assert users.get_user_by_id(registered["user"]["id"])["is_active"] is False
