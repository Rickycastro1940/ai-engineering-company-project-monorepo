from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DATA_DIR", str(tmp_path / "auth"))
    monkeypatch.setenv("AUTH_INCLUDE_RESET_LINK_IN_RESPONSE", "true")
    from api.app import app
    import auth

    sent_emails = []

    def fake_send_reset_email(email: str, reset_url: str) -> dict[str, str]:
        sent_emails.append({"email": email, "reset_url": reset_url})
        return {
            "delivery_status": "sent",
            "provider": "resend",
            "message_id": "test-message-id",
        }

    monkeypatch.setattr(auth, "_send_reset_email", fake_send_reset_email)

    return TestClient(app), sent_emails


def _extract_token(reset_url: str) -> str:
    parsed = urlparse(reset_url)
    token = parse_qs(parsed.query).get("token", [""])[0]
    assert token
    return token


def test_forgot_password_uses_generic_response_for_unknown_email(auth_client):
    client, sent_emails = auth_client
    response = client.post("/auth/forgot-password", json={"email": "missing@example.com"})

    assert response.status_code == 200
    assert response.json() == {
        "message": "If an account exists for that email, a password reset link has been sent."
    }
    assert sent_emails == []


def test_reset_password_updates_login_and_consumes_token(auth_client, tmp_path):
    client, sent_emails = auth_client
    old_password = "old-pass-1"
    new_password = "new-pass-2"
    register_response = client.post(
        "/auth/register",
        json={"email": "User@Example.com", "password": old_password},
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == "user@example.com"

    forgot_response = client.post("/auth/forgot-password", json={"email": "user@example.com"})
    assert forgot_response.status_code == 200
    reset_url = forgot_response.json()["reset_url"]
    token = _extract_token(reset_url)
    assert sent_emails == [{"email": "user@example.com", "reset_url": reset_url}]

    outbox = json.loads((tmp_path / "auth" / "password_reset_outbox.json").read_text(encoding="utf-8"))
    assert outbox[-1]["email"] == "user@example.com"
    assert outbox[-1]["reset_url"] == reset_url
    assert outbox[-1]["delivery_status"] == "sent"
    assert outbox[-1]["provider"] == "resend"
    assert outbox[-1]["message_id"] == "test-message-id"

    reset_response = client.post("/auth/reset-password", json={"token": token, "new_password": new_password})
    assert reset_response.status_code == 200

    old_login_response = client.post("/auth/login", json={"email": "user@example.com", "password": old_password})
    assert old_login_response.status_code == 401

    new_login_response = client.post("/auth/login", json={"email": "user@example.com", "password": new_password})
    assert new_login_response.status_code == 200

    reused_response = client.post("/auth/reset-password", json={"token": token, "new_password": "another-pass-3"})
    assert reused_response.status_code == 400


def test_expired_reset_token_is_rejected(auth_client, tmp_path):
    client, _sent_emails = auth_client
    password = "start-pass-1"
    client.post("/auth/register", json={"email": "user@example.com", "password": password})
    forgot_response = client.post("/auth/forgot-password", json={"email": "user@example.com"})
    token = _extract_token(forgot_response.json()["reset_url"])

    tokens_file = tmp_path / "auth" / "password_reset_tokens.json"
    tokens = json.loads(tokens_file.read_text(encoding="utf-8"))
    tokens[0]["expires_at"] = "2000-01-01T00:00:00+00:00"
    tokens_file.write_text(json.dumps(tokens), encoding="utf-8")

    reset_response = client.post("/auth/reset-password", json={"token": token, "new_password": "new-pass-2"})
    assert reset_response.status_code == 400

    login_response = client.post("/auth/login", json={"email": "user@example.com", "password": password})
    assert login_response.status_code == 200


def test_tampered_reset_token_is_rejected(auth_client):
    client, _sent_emails = auth_client
    client.post("/auth/register", json={"email": "user@example.com", "password": "start-pass-1"})
    forgot_response = client.post("/auth/forgot-password", json={"email": "user@example.com"})
    token = _extract_token(forgot_response.json()["reset_url"])
    tampered_token = f"{token}tampered"

    reset_response = client.post(
        "/auth/reset-password",
        json={"token": tampered_token, "new_password": "new-pass-2"},
    )

    assert reset_response.status_code == 400
