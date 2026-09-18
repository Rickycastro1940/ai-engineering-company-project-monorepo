"""Password hashing and JWT subject rules used by staff sessions."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from jose import jwt

from test.conftest import auth


def test_password_hash_is_not_reversible_plaintext() -> None:
    hashed = auth.hash_password("secret-password")
    assert hashed != "secret-password"
    assert auth.verify_password("secret-password", hashed) is True
    assert auth.verify_password("other-password", hashed) is False


def test_access_token_subject_round_trips_the_user_id() -> None:
    assert auth.decode_access_token(auth.create_access_token("42")) == "42"


def test_token_without_a_user_subject_is_not_a_session() -> None:
    token = jwt.encode({"sub": None}, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
    with pytest.raises(Exception):
        auth.decode_access_token(token)


def test_signing_secret_comes_from_the_environment_not_a_hardcoded_default() -> None:
    with patch.dict("os.environ", {"JWT_SECRET_KEY": "brasaland-test-secret"}, clear=False):
        assert auth._load_secret_key() == "brasaland-test-secret"
    with patch.dict("os.environ", {}, clear=True):
        generated = auth._load_secret_key()
    # Reloads must not fall back to a known development placeholder.
    assert generated != "change-this-development-secret"
    assert len(generated) >= 32
