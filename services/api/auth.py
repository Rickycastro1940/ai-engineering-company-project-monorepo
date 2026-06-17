from __future__ import annotations

from auth_store import (
    consume_reset_token,
    create_reset_token,
    find_user,
    verify_credentials,
)
from email_client import send_reset_email
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/auth", tags=["auth"])

CONFIRMATION_MESSAGE = "If that address is registered, you'll receive a link shortly."


def _validate_email(value: str) -> str:
    candidate = (value or "").strip()
    if "@" not in candidate or candidate.startswith("@") or candidate.endswith("@") or " " in candidate:
        raise ValueError("A valid email address is required.")
    return candidate


class ForgotPasswordRequest(BaseModel):
    email: str

    _check_email = field_validator("email")(_validate_email)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)

    _check_email = field_validator("email")(_validate_email)


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest) -> dict[str, str]:
    user = find_user(body.email)
    if user is not None:
        token = create_reset_token(body.email)
        send_reset_email(body.email, token)
    return {"message": CONFIRMATION_MESSAGE}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest) -> dict[str, str]:
    if not consume_reset_token(body.token, body.password):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    return {"message": "Your password has been updated."}


@router.post("/login")
def login(body: LoginRequest) -> dict[str, str]:
    if not verify_credentials(body.email, body.password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"message": "Logged in successfully."}
