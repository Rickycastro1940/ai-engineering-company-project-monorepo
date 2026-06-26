import pytest
from unittest.mock import MagicMock
# Replace 'app' or your module name with your actual import paths
from app import register_user, UserDuplicateError, ValidationError

# 1. HAPPY PATH
def test_register_user_success():
    """Test that a new user with valid, unique credentials registers successfully."""
    mock_db = MagicMock()
    # Assume your DB lookup returns None (user doesn't exist yet)
    mock_db.get_user_by_email.return_value = None
    mock_db.create_user.return_value = {"email": "ricardo@example.com", "id": 1

    result = register_user(mock_db, "ricardo@example.com", "SecurePassword123")

    assert result["email"] == "ricardo@example.com"
    mock_db.create_user.assert_called_once()

# 2. EDGE CASE
def test_register_user_empty_fields():
    """Test that registering with empty fields triggers a Validation Error."""
    mock_db = MagicMock()

    with pytest.raises(ValidationError):
        register_user(mock_db, "", "SecurePassword123")

# 3. FAILURE MODE
def test_register_user_duplicate_email():
    """Test that registering an already registered email throws an exception."""
    mock_db = MagicMock()
    # Simulate that the user already exists in your database
    mock_db.get_user_by_email.return_value = {"email": "ricardo@example.com"

    with pytest.raises(UserDuplicateError):
        register_user(mock_db, "ricardo@example.com", "AnotherPassword123")