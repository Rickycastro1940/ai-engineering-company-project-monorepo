"""Staff user rules: unique email, password change, and who may act on whom."""

from __future__ import annotations

from test.conftest import PASSWORD, granted_identity, register_user, refused_session, users


def test_admin_may_read_another_staff_record(client) -> None:
    admin = register_user(client, "admin@brasaland.test")
    member = register_user(client, "member@brasaland.test")
    listed = client.get("/users", headers={"Authorization": f"Bearer {admin['access_token']}"})
    emails = {row["email"] for row in listed.json()}
    assert emails == {"admin@brasaland.test", "member@brasaland.test"}

    read = client.get(
        f"/users/{member['user']['id']}",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    assert read.json()["email"] == "member@brasaland.test"


def test_password_change_replaces_the_credential_used_to_log_in(client) -> None:
    member = register_user(client, "member@brasaland.test")
    client.put(
        f"/users/{member['user']['id']}",
        json={"password": "new-secret-password"},
        headers={"Authorization": f"Bearer {member['access_token']}"},
    )
    assert users.authenticate_user("member@brasaland.test", "new-secret-password") is not None
    assert users.authenticate_user("member@brasaland.test", PASSWORD) is None

    login = client.post(
        "/auth/login",
        json={"email": "member@brasaland.test", "password": "new-secret-password"},
    )
    identity = granted_identity(client, login.json()["access_token"])
    assert identity["email"] == "member@brasaland.test"


def test_member_cannot_take_another_mailbox_or_delete_another_account(client) -> None:
    register_user(client, "admin@brasaland.test")
    member = register_user(client, "member@brasaland.test")
    other = register_user(client, "other@brasaland.test")
    headers = {"Authorization": f"Bearer {member['access_token']}"}

    conflict = client.put(f"/users/{member['user']['id']}", json={"email": "other@brasaland.test"}, headers=headers)
    assert conflict.status_code == 409
    assert users.get_user_by_email("member@brasaland.test") is not None
    assert users.get_user_by_id(member["user"]["id"])["email"] == "member@brasaland.test"

    blocked = client.delete(f"/users/{other['user']['id']}", headers=headers)
    refused_session(blocked)
    assert blocked.status_code == 403
    assert users.get_user_by_id(other["user"]["id"]) is not None


def test_short_password_does_not_create_a_user(client) -> None:
    response = client.post("/users", json={"email": "ops@brasaland.test", "password": "short"})
    assert users.count_users() == 0
    assert response.status_code != 201


def test_anonymous_cannot_read_kitchen_stock(client) -> None:
    anonymous = client.get("/inventory")
    refused_session(anonymous)
    staff = register_user(client, "ops@brasaland.test")
    stock = client.get("/inventory", headers={"Authorization": f"Bearer {staff['access_token']}"})
    assert isinstance(stock.json(), list)
