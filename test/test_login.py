"""POST /auth/login — who may start a staff session."""

from __future__ import annotations

from test.conftest import PASSWORD, granted_identity, register_user, refused_session, users


def test_login_starts_session_for_known_password(client) -> None:
    register_user(client, "camila.ospina@brasaland.test")
    response = client.post(
        "/auth/login",
        json={"email": "camila.ospina@brasaland.test", "password": PASSWORD},
    )
    identity = granted_identity(client, response.json()["access_token"])
    assert identity["email"] == "camila.ospina@brasaland.test"


def test_login_treats_email_as_case_insensitive(client) -> None:
    register_user(client, "ashley.turner@brasaland.test")
    response = client.post(
        "/auth/login",
        json={"email": "Ashley.Turner@Brasaland.test", "password": PASSWORD},
    )
    identity = granted_identity(client, response.json()["access_token"])
    assert identity["email"] == "ashley.turner@brasaland.test"


def test_login_denies_unknown_email_and_wrong_password_the_same_way(client) -> None:
    register_user(client, "ops@brasaland.test")
    unknown = client.post(
        "/auth/login",
        json={"email": "missing@brasaland.test", "password": PASSWORD},
    )
    wrong = client.post(
        "/auth/login",
        json={"email": "ops@brasaland.test", "password": "wrong-password"},
    )
    refused_session(unknown)
    refused_session(wrong)
    # authenticate_user returns None for both: do not leak which mailbox exists.
    assert users.authenticate_user("missing@brasaland.test", PASSWORD) is None
    assert users.authenticate_user("ops@brasaland.test", "wrong-password") is None


def test_login_denies_inactive_staff(client) -> None:
    registered = register_user(client, "ops@brasaland.test")
    users.update_user(registered["user"]["id"], is_active=False)
    response = client.post(
        "/auth/login",
        json={"email": "ops@brasaland.test", "password": PASSWORD},
    )
    refused_session(response)
    # Password still verifies; the account is simply not allowed to sign in.
    assert users.authenticate_user("ops@brasaland.test", PASSWORD) is not None
    assert users.get_user_by_email("ops@brasaland.test")["is_active"] is False
