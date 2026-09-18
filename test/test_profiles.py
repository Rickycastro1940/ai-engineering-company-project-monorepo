"""PUT /profiles/me — which contact fields a staff member may change."""

from __future__ import annotations

from test.conftest import granted_identity, register_user, refused_session, users


def test_profile_update_writes_contact_fields_for_the_session_user(client) -> None:
    token = register_user(client, "felipe.guerrero@brasaland.test")["access_token"]
    client.put(
        "/profiles/me",
        json={"name": "Felipe Guerrero", "phone": "+57 300 000 0000", "address": "Medellín HQ"},
        headers={"Authorization": f"Bearer {token}"},
    )
    identity = granted_identity(client, token)
    stored = users.get_user_by_email("felipe.guerrero@brasaland.test")
    assert identity["name"] == stored["name"] == "Felipe Guerrero"
    assert identity["phone"] == stored["phone"] == "+57 300 000 0000"
    assert identity["address"] == stored["address"] == "Medellín HQ"
    assert identity["email"] == "felipe.guerrero@brasaland.test"


def test_profile_partial_update_keeps_untouched_fields_and_clears_blank_name(client) -> None:
    token = register_user(client, "ops@brasaland.test", name="Kitchen Lead")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.put("/profiles/me", json={"phone": "+1 305 555 0100"}, headers=headers)
    after_phone = users.get_user_by_email("ops@brasaland.test")
    assert after_phone["name"] == "Kitchen Lead"
    assert after_phone["phone"] == "+1 305 555 0100"

    client.put("/profiles/me", json={"name": "   "}, headers=headers)
    after_blank = users.get_user_by_email("ops@brasaland.test")
    assert after_blank["name"] is None  # blank contact fields are stored empty, not a space
    assert after_blank["phone"] == "+1 305 555 0100"


def test_profile_requires_a_session_and_cannot_grant_admin(client) -> None:
    refused_session(client.put("/profiles/me", json={"name": "Felipe Guerrero"}))

    register_user(client, "admin@brasaland.test")
    member = register_user(client, "member@brasaland.test")
    client.put(
        "/profiles/me",
        json={"name": "Member", "is_admin": True},
        headers={"Authorization": f"Bearer {member['access_token']}"},
    )
    stored = users.get_user_by_email("member@brasaland.test")
    # ProfileUpdate ignores role fields; a member cannot self-promote.
    assert stored["is_admin"] is False
    assert stored["name"] == "Member"
