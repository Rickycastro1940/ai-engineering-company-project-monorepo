"""POST /auth/register — who may create a staff account and start a session.

Happy / edge / failure cases for AUTH-088 (Building Bullet-Proof Applications).
"""

from __future__ import annotations

from tests.auth_helpers import PASSWORD, register_session, session_identity, users


def test_register_grants_session_and_hashes_password(client) -> None:
    """Happy: valid credentials create a staff row and return a usable session."""
    payload = register_session(client, "felipe.guerrero@brasaland.test", name="Felipe Guerrero")

    assert payload["user"]["email"] == "felipe.guerrero@brasaland.test"
    assert payload["user"]["name"] == "Felipe Guerrero"
    assert payload["user"]["is_active"] is True
    # First account on an empty store becomes admin so HQ can onboard the rest.
    assert payload["user"]["is_admin"] is True

    stored = users.get_user_by_email("felipe.guerrero@brasaland.test")
    assert stored is not None
    assert stored["hashed_password"] != PASSWORD
    assert users.verify_password(PASSWORD, stored["hashed_password"])

    identity = session_identity(client, payload["access_token"])
    assert identity["email"] == "felipe.guerrero@brasaland.test"


def test_register_lowercases_email_and_only_first_user_is_admin(client) -> None:
    """Edge: mailbox is normalised; the second registrant stays a member."""
    first = register_session(client, "Admin@Brasaland.test")
    second = register_session(client, "Camila.Ospina@Brasaland.test")

    assert first["user"]["email"] == "admin@brasaland.test"
    assert first["user"]["is_admin"] is True
    assert second["user"]["email"] == "camila.ospina@brasaland.test"
    assert second["user"]["is_admin"] is False


def test_register_rejects_duplicate_mailbox(client) -> None:
    """Failure: a second registration for the same mailbox creates no new session."""
    register_session(client, "ops@brasaland.test")
    before = users.count_users()

    response = client.post(
        "/auth/register",
        json={"email": "OPS@brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 409
    assert not response.json().get("access_token")
    assert users.count_users() == before


def test_register_rejects_short_password_without_creating_a_row(client) -> None:
    """Failure: password below the eight-character floor leaves the store empty."""
    response = client.post(
        "/auth/register",
        json={"email": "short@brasaland.test", "password": "short"},
    )

    assert response.status_code == 422
    assert users.count_users() == 0
