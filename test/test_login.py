"""POST /auth/login — JSON credentials for the staff console."""

from __future__ import annotations

from test.conftest import PASSWORD, register_user, users


def test_login_happy_path_returns_token_for_valid_credentials(client) -> None:
    register_user(client, "camila.ospina@brasaland.test")

    response = client.post(
        "/auth/login",
        json={"email": "camila.ospina@brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["email"] == "camila.ospina@brasaland.test"
    assert "access_token" in payload
    assert "hashed_password" not in payload["user"]


def test_login_edge_accepts_mixed_case_email(client) -> None:
    register_user(client, "ashley.turner@brasaland.test")

    response = client.post(
        "/auth/login",
        json={"email": "Ashley.Turner@Brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "ashley.turner@brasaland.test"


def test_login_failure_unknown_email_and_wrong_password_share_401(client) -> None:
    register_user(client, "ops@brasaland.test")

    unknown = client.post(
        "/auth/login",
        json={"email": "missing@brasaland.test", "password": PASSWORD},
    )
    wrong = client.post(
        "/auth/login",
        json={"email": "ops@brasaland.test", "password": "wrong-password"},
    )

    assert unknown.status_code == 401
    assert wrong.status_code == 401
    assert "access_token" not in unknown.json()
    assert unknown.json().get("code") == wrong.json().get("code") == "unauthorized"


def test_login_failure_inactive_user(client) -> None:
    registered = register_user(client, "ops@brasaland.test")
    users.update_user(registered["user"]["id"], is_active=False)

    response = client.post(
        "/auth/login",
        json={"email": "ops@brasaland.test", "password": PASSWORD},
    )
    assert response.status_code == 401


def test_login_failure_empty_email_is_malformed(client) -> None:
    response = client.post("/auth/login", json={"email": "", "password": PASSWORD})
    assert response.status_code == 422
