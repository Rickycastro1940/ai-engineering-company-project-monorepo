import pytest
import time
from app import create_access_token, decode_and_verify_token, TokenExpiredError, InvalidTokenError

# 1. HAPPY PATH
def test_token_generation_and_verification_success():
    """Test that a fresh token is correctly created and verified."""
    payload = {"sub": "ricardo@example.com"
    # Generate token valid for 10 minutes
    token = create_access_token(data=payload, expires_delta=600)

    decoded_payload = decode_and_verify_token(token)
    assert decoded_payload["sub"] == "ricardo@example.com"

# 2. EDGE CASE
def test_token_verification_malformed_signature():
    """Test passing a completely malformed token or modified signature."""
    bad_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.badpayload.badsignature"

    with pytest.raises(InvalidTokenError):
        decode_and_verify_token(bad_token)

# 3. FAILURE MODE (The Regression Catch!)
def test_token_verification_expired():
    """Ensure that an expired token throws TokenExpiredError instead of letting users lock out."""
    payload = {"sub": "ricardo@example.com"
    # Force generating a token that expired in the past
    expired_token = create_access_token(data=payload, expires_delta=-10)

    with pytest.raises(TokenExpiredError):
        decode_and_verify_token(expired_token)