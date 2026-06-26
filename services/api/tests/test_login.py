import pytest
from unittest.mock import MagicMock
from main import authenticate_user, InvalidCredentialsError, ValidationError

@pytest.fixture
def mock_db():
    return MagicMock()

def test_authenticate_user_success(mock_db):
    mock_db.get_user_by_email.return_value = {
        "email": "ricardo@example.com",
        "hashed_password": "mocked_hashed_string"


    # Mocking password verification to succeed
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("auth.verify_password", lambda p, h: True)
        user = authenticate_user("ricardo@example.com", "password123", mock_db)
        assert user["email"] == "ricardo@example.com"

def test_authenticate_user_invalid_password(mock_db):
    mock_db.get_user_by_email.return_value = {
        "email": "ricardo@example.com",
        "hashed_password": "mocked_hashed_string"
        }

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("auth.verify_password", lambda p, h: False)
        with pytest.raises(InvalidCredentialsError):
            authenticate_user("ricardo@example.com", "wrongpassword", mock_db)

def test_authenticate_user_not_found(mock_db):
    mock_db.get_user_by_email.return_value = None

    with pytest.raises(InvalidCredentialsError):
        authenticate_user("nonexistent@example.com", "password123", mock_db)
