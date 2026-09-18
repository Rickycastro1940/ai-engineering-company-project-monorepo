"""POST /auth/register — who gets a staff account, and with which role."""

from __future__ import annotations

from test.conftest import PASSWORD, granted_identity, register_user, users


def test_register_creates_active_session_for_named_staff(client) -> None:
    payload = register_user(
        client,
        "felipe.guerrero@brasaland.test",
        name="Felipe Guerrero",
    )
    identity = granted_identity(client, payload["access_token"])
    stored = users.get_user_by_email("felipe.guerrero@brasaland.test")

    assert identity["email"] == "felipe.guerrero@brasaland.test"
    assert identity["name"] == "Felipe Guerrero"
    assert identity["is_admin"] is True
    assert stored is not None
    assert stored["hashed_password"] != PASSWORD
    assert users.verify_password(PASSWORD, stored["hashed_password"])


def test_register_lowercases_email_and_only_first_account_is_admin(client) -> None:
    first = register_user(client, "Admin@Brasaland.test", name="   ")
    second = register_user(client, "lucia.fernandez@brasaland.test")

    assert first["user"]["email"] == "admin@brasaland.test"
    assert first["user"]["is_admin"] is True
    assert first["user"]["name"] is None
    assert second["user"]["is_admin"] is False
    assert users.count_users() == 2


def test_register_rejects_duplicate_mailbox_and_keeps_one_account(client) -> None:
    register_user(client, "ops@brasaland.test")
    duplicate = client.post(
        "/auth/register",
        json={"email": "OPS@brasaland.test", "password": PASSWORD},
    )

    assert duplicate.status_code == 409
    assert not duplicate.json().get("access_token")
    assert users.count_users() == 1


def test_register_does_not_create_account_when_password_is_too_short(client) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "kitchen@brasaland.test", "password": "short"},
    )

    assert users.count_users() == 0
    assert users.get_user_by_email("kitchen@brasaland.test") is None
    assert response.status_code != 201
