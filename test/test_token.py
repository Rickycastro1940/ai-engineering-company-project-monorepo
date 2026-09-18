"""POST /auth/token — form login still authenticates by email."""

from __future__ import annotations

from test.conftest import PASSWORD, granted_identity, register_user, refused_session, users


def test_token_login_identifies_the_same_staff_account(client) -> None:
    register_user(client, "nicolas.park@brasaland.test")
    response = client.post(
        "/auth/token",
        data={"username": "nicolas.park@brasaland.test", "password": PASSWORD},
    )
    identity = granted_identity(client, response.json()["access_token"])
    assert identity["email"] == "nicolas.park@brasaland.test"


def test_token_login_accepts_mixed_case_email_as_username(client) -> None:
    register_user(client, "mariana.restrepo@brasaland.test")
    response = client.post(
        "/auth/token",
        data={"username": "Mariana.Restrepo@brasaland.test", "password": PASSWORD},
    )
    identity = granted_identity(client, response.json()["access_token"])
    assert identity["email"] == "mariana.restrepo@brasaland.test"


def test_token_login_denies_wrong_password(client) -> None:
    register_user(client, "ops@brasaland.test")
    response = client.post(
        "/auth/token",
        data={"username": "ops@brasaland.test", "password": "not-the-password"},
    )
    refused_session(response)
    assert users.authenticate_user("ops@brasaland.test", "not-the-password") is None


def test_token_login_denies_inactive_staff(client) -> None:
    registered = register_user(client, "ops@brasaland.test")
    users.update_user(registered["user"]["id"], is_active=False)
    response = client.post(
        "/auth/token",
        data={"username": "ops@brasaland.test", "password": PASSWORD},
    )
    refused_session(response)
    assert users.get_user_by_email("ops@brasaland.test")["is_active"] is False
