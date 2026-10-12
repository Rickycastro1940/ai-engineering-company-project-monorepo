"""POST /auth/login — who may start a staff session with JSON credentials.

Happy / edge / failure cases for AUTH-088 (Building Bullet-Proof Applications).
"""

from __future__ import annotations

from tests.auth_helpers import (
    PASSWORD,
    refused_session,
    register_session,
    session_identity,
    users,
)


def test_login_starts_session_for_known_password(client) -> None:
    """Happy: a known mailbox + password grants a session for that staff member."""
    register_session(client, "camila.ospina@brasaland.test")

    response = client.post(
        "/auth/login",
        json={"email": "camila.ospina@brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    identity = session_identity(client, response.json()["access_token"])
    assert identity["email"] == "camila.ospina@brasaland.test"


def test_login_treats_email_as_case_insensitive(client) -> None:
    """Edge: mixed-case email still finds the normalised mailbox."""
    register_session(client, "ashley.turner@brasaland.test")

    response = client.post(
        "/auth/login",
        json={"email": "Ashley.Turner@Brasaland.test", "password": PASSWORD},
    )

    assert response.status_code == 200
    identity = session_identity(client, response.json()["access_token"])
    assert identity["email"] == "ashley.turner@brasaland.test"


def test_login_denies_unknown_email_and_wrong_password_the_same_way(client) -> None:
    """Failure: unknown mailbox and wrong password both refuse a session.

    authenticate_user returns None for both so callers cannot probe which
    mailboxes exist (AI-suggested case — see TESTING.md).
    """
    register_session(client, "ops@brasaland.test")

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
    assert users.authenticate_user("missing@brasaland.test", PASSWORD) is None
    assert users.authenticate_user("ops@brasaland.test", "wrong-password") is None


def test_login_denies_inactive_staff(client) -> None:
    """Failure: deactivated staff keep a valid password hash but cannot sign in."""
    registered = register_session(client, "ops@brasaland.test")
    users.update_user(registered["user"]["id"], is_active=False)

    response = client.post(
        "/auth/login",
        json={"email": "ops@brasaland.test", "password": PASSWORD},
    )

    refused_session(response)
    # Password still verifies; the account is simply not allowed to sign in.
    assert users.authenticate_user("ops@brasaland.test", PASSWORD) is not None
    assert users.get_user_by_email("ops@brasaland.test")["is_active"] is False
