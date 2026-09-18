"""Authenticated /users CRUD — missed RBAC and duplicate-update cases."""

from __future__ import annotations

from test.conftest import PASSWORD, register_user


def test_users_happy_path_admin_lists_and_reads(client) -> None:
    admin = register_user(client, "admin@brasaland.test")
    member = register_user(client, "member@brasaland.test")
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    listed = client.get("/users", headers=headers)
    assert listed.status_code == 200
    assert [user["id"] for user in listed.json()] == [admin["user"]["id"], member["user"]["id"]]

    read = client.get(f"/users/{member['user']['id']}", headers=headers)
    assert read.status_code == 200
    assert read.json()["email"] == "member@brasaland.test"


def test_users_edge_new_password_logs_in(client) -> None:
    member = register_user(client, "member@brasaland.test")
    headers = {"Authorization": f"Bearer {member['access_token']}"}

    updated = client.put(
        f"/users/{member['user']['id']}",
        json={"password": "new-secret-password"},
        headers=headers,
    )
    assert updated.status_code == 200

    login = client.post(
        "/auth/login",
        json={"email": "member@brasaland.test", "password": "new-secret-password"},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]

    old = client.post(
        "/auth/login",
        json={"email": "member@brasaland.test", "password": PASSWORD},
    )
    assert old.status_code == 401


def test_users_failure_duplicate_email_on_update_and_member_cannot_delete_other(client) -> None:
    register_user(client, "admin@brasaland.test")
    member = register_user(client, "member@brasaland.test")
    other = register_user(client, "other@brasaland.test")
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}

    conflict = client.put(
        f"/users/{member['user']['id']}",
        json={"email": "other@brasaland.test"},
        headers=member_headers,
    )
    assert conflict.status_code == 409

    blocked = client.delete(f"/users/{other['user']['id']}", headers=member_headers)
    assert blocked.status_code == 403


def test_users_create_rejects_short_password(client) -> None:
    response = client.post("/users", json={"email": "ops@brasaland.test", "password": "short"})
    assert response.status_code == 422
