"""Unit tests for JWT/password helpers in ``services/api/auth.py``."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from jose import jwt

from test.conftest import auth


def test_hash_and_verify_password_round_trip() -> None:
    hashed = auth.hash_password("secret-password")
    assert hashed != "secret-password"
    assert auth.verify_password("secret-password", hashed) is True
    assert auth.verify_password("other-password", hashed) is False


def test_create_and_decode_access_token_round_trip() -> None:
    token = auth.create_access_token("42")
    assert auth.decode_access_token(token) == "42"


def test_decode_access_token_rejects_missing_subject() -> None:
    token = jwt.encode({"sub": None}, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
    with pytest.raises(Exception) as error:
        auth.decode_access_token(token)
    assert getattr(error.value, "status_code", None) == 401


def test_secret_and_expiry_come_from_environment() -> None:
    with patch.dict("os.environ", {"JWT_SECRET_KEY": "brasaland-test-secret"}, clear=False):
        assert auth._load_secret_key() == "brasaland-test-secret"
    with patch.dict("os.environ", {"ACCESS_TOKEN_EXPIRE_MINUTES": "15"}, clear=False):
        assert auth._load_access_token_expire_minutes() == 15
    with patch.dict("os.environ", {}, clear=True):
        generated = auth._load_secret_key()
    assert len(generated) >= 32
