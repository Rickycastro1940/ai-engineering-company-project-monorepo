"""POST /auth/register — staff onboarding."""

from __future__ import annotations

from test.conftest import PASSWORD, register_user


def test_register_happy_path_returns_bearer_token_and_public_user(client) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "felipe.guerrero@brasaland.test",
            "password": PASSWORD,
            "name": "Felipe Guerrero",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["email"] == "felipe.guerrero@brasaland.test"
    assert payload["user"]["name"] == "Felipe Guerrero"
    assert "hashed_password" not in payload["user"]


def test_register_edge_second_user_is_not_admin_and_blank_name_is_null(client) -> None:
    first = register_user(client, "Admin@Brasaland.test", name="   ")
    second = register_user(client, "lucia.fernandez@brasaland.test")

    assert first["user"]["email"] == "admin@brasaland.test"
    assert first["user"]["is_admin"] is True
    assert first["user"]["name"] is None
    assert second["user"]["is_admin"] is False


def test_register_failure_duplicate_email_and_short_password(client) -> None:
    register_user(client, "ops@brasaland.test")

    duplicate = client.post(
        "/auth/register",
        json={"email": "OPS@brasaland.test", "password": PASSWORD},
    )
    assert duplicate.status_code == 409

    short = client.post(
        "/auth/register",
        json={"email": "kitchen@brasaland.test", "password": "short"},
    )
    assert short.status_code == 422
