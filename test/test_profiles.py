"""PUT /profiles/me — contact fields on the authenticated staff user."""

from __future__ import annotations

from test.conftest import register_user


def test_profiles_me_happy_path_updates_contact_fields(client) -> None:
    token = register_user(client, "felipe.guerrero@brasaland.test")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.put(
        "/profiles/me",
        json={"name": "Felipe Guerrero", "phone": "+57 300 000 0000", "address": "Medellín HQ"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Felipe Guerrero"
    assert body["phone"] == "+57 300 000 0000"
    assert body["address"] == "Medellín HQ"
    assert body["email"] == "felipe.guerrero@brasaland.test"


def test_profiles_me_edge_partial_update_and_blank_name(client) -> None:
    token = register_user(client, "ops@brasaland.test", name="Kitchen Lead")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    phone_only = client.put("/profiles/me", json={"phone": "+1 305 555 0100"}, headers=headers)
    assert phone_only.status_code == 200
    assert phone_only.json()["name"] == "Kitchen Lead"
    assert phone_only.json()["phone"] == "+1 305 555 0100"

    blank = client.put("/profiles/me", json={"name": "   "}, headers=headers)
    assert blank.status_code == 200
    assert blank.json()["name"] is None
    assert blank.json()["phone"] == "+1 305 555 0100"


def test_profiles_me_failure_anonymous_and_cannot_escalate(client) -> None:
    anonymous = client.put("/profiles/me", json={"name": "Felipe Guerrero"})
    assert anonymous.status_code == 401

    register_user(client, "admin@brasaland.test")
    member = register_user(client, "member@brasaland.test")
    member_headers = {"Authorization": f"Bearer {member['access_token']}"}
    denied = client.put(
        "/profiles/me",
        json={"name": "Member", "is_admin": True},
        headers=member_headers,
    )
    assert denied.status_code == 200
    assert denied.json()["is_admin"] is False
