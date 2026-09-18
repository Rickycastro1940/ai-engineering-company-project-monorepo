"""POST /auth/token — OAuth2 password form used by OpenAPI Authorize."""

from __future__ import annotations

from test.conftest import PASSWORD, register_user, users


def test_token_happy_path_form_login_returns_bearer_access_token(client) -> None:
    register_user(client, "nicolas.park@brasaland.test")

    response = client.post(
        "/auth/token",
        data={"username": "nicolas.park@brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert "user" not in payload


def test_token_edge_username_field_is_email(client) -> None:
    register_user(client, "mariana.restrepo@brasaland.test")

    response = client.post(
        "/auth/token",
        data={"username": "Mariana.Restrepo@brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "mariana.restrepo@brasaland.test"


def test_token_failure_wrong_password_and_missing_field(client) -> None:
    register_user(client, "ops@brasaland.test")

    wrong = client.post(
        "/auth/token",
        data={"username": "ops@brasaland.test", "password": "not-the-password"},
    )
    assert wrong.status_code == 401
    assert "access_token" not in wrong.json()

    malformed = client.post("/auth/token", data={"username": "ops@brasaland.test"})
    assert malformed.status_code == 422


def test_token_failure_inactive_user(client) -> None:
    registered = register_user(client, "ops@brasaland.test")
    users.update_user(registered["user"]["id"], is_active=False)

    response = client.post(
        "/auth/token",
        data={"username": "ops@brasaland.test", "password": PASSWORD},
    )
    assert response.status_code == 401
