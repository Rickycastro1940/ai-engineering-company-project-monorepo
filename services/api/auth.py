from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
USERS_FILE = Path(os.getenv("AUTH_USERS_FILE", REPO_ROOT / "data" / "users.json"))
JWT_SECRET = os.getenv("AUTH_JWT_SECRET", "dev-auth-secret-change-me")
JWT_TTL_SECONDS = int(os.getenv("AUTH_JWT_TTL_SECONDS", "86400"))
HASH_ITERATIONS = 200_000

bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class ProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid email is required")
    return normalized


def _read_users() -> dict[str, dict[str, Any]]:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail="Unable to read user store") from error


def _write_users(users: dict[str, dict[str, Any]]) -> None:
    try:
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        USERS_FILE.write_text(json.dumps(users, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as error:
        raise HTTPException(status_code=500, detail="Unable to write user store") from error


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(HASH_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_value, digest_value = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected_digest)


def _encode_segment(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_segment(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


def _sign_token(message: str) -> str:
    return base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode("utf-8"), message.encode("ascii"), hashlib.sha256).digest()).rstrip(b"=").decode("ascii")


def create_token(user: dict[str, Any]) -> str:
    now = int(time.time())
    header = _encode_segment({"alg": "HS256", "typ": "JWT"})
    payload = _encode_segment({"sub": user["email"], "iat": now, "exp": now + JWT_TTL_SECONDS})
    message = f"{header}.{payload}"
    return f"{message}.{_sign_token(message)}"


def _public_user(user: dict[str, Any]) -> dict[str, str]:
    return {"id": user["email"], "email": user["email"], "name": user["name"], "created_at": user["created_at"]}


def _auth_response(user: dict[str, Any]) -> dict[str, Any]:
    return {"token": create_token(user), "user": _public_user(user)}


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        header, payload, signature = credentials.credentials.split(".", 2)
        message = f"{header}.{payload}"
        if not hmac.compare_digest(signature, _sign_token(message)):
            raise ValueError("invalid signature")
        claims = _decode_segment(payload)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None
    if int(claims.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    user = _read_users().get(str(claims.get("sub", "")))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest) -> dict[str, Any]:
    email = _normalize_email(body.email)
    users = _read_users()
    if email in users:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    user = {
        "email": email,
        "name": body.name.strip(),
        "password_hash": _hash_password(body.password),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    users[email] = user
    _write_users(users)
    return _auth_response(user)


@router.post("/login")
def login(body: LoginRequest) -> dict[str, Any]:
    email = _normalize_email(body.email)
    user = _read_users().get(email)
    if user is None or not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return _auth_response(user)


@router.get("/me")
def read_profile(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    return _public_user(current_user)


@router.patch("/me")
def update_profile(body: ProfileUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    users = _read_users()
    user = users[current_user["email"]]
    user["name"] = body.name.strip()
    _write_users(users)
    return _public_user(user)


@users_router.put("/{user_id}")
def update_user(user_id: str, body: ProfileUpdateRequest, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    if user_id != current_user["email"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot update another user")
    users = _read_users()
    user = users[current_user["email"]]
    user["name"] = body.name.strip()
    _write_users(users)
    return _public_user(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChangeRequest, current_user: dict[str, Any] = Depends(get_current_user)) -> None:
    users = _read_users()
    user = users[current_user["email"]]
    if not _verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user["password_hash"] = _hash_password(body.new_password)
    _write_users(users)
