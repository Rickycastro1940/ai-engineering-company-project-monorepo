from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 210_000
RESET_TOKEN_TTL_MINUTES = 60
GENERIC_RESET_MESSAGE = "If an account exists for that email, a password reset link has been sent."

_storage_lock = threading.Lock()

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20)
    password: str = Field(min_length=8, max_length=128)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _auth_data_dir() -> Path:
    configured = os.getenv("AUTH_DATA_DIR")
    return Path(configured).expanduser().resolve() if configured else REPO_ROOT / "data" / "auth"


def _users_file() -> Path:
    return _auth_data_dir() / "users.json"


def _reset_tokens_file() -> Path:
    return _auth_data_dir() / "password_reset_tokens.json"


def _reset_outbox_file() -> Path:
    return _auth_data_dir() / "password_reset_outbox.json"


def _read_json(path: Path, default: list[dict[str, str]]) -> list[dict[str, str]]:
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail=f"Unable to read auth storage: {path.name}") from error
    if not isinstance(payload, list):
        raise HTTPException(status_code=500, detail=f"Invalid auth storage format: {path.name}")
    return payload


def _write_json(path: Path, payload: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(path)
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Unable to write auth storage: {path.name}") from error


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    return normalized


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
    return "$".join(
        [
            PASSWORD_HASH_SCHEME,
            str(PASSWORD_HASH_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations, salt_value, digest_value = password_hash.split("$", 3)
        if scheme != PASSWORD_HASH_SCHEME:
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _find_user(users: list[dict[str, str]], email: str) -> dict[str, str] | None:
    for user in users:
        if user.get("email") == email:
            return user
    return None


def _reset_url(token: str) -> str:
    configured_base = os.getenv("FRONTEND_URL", "").rstrip("/")
    path = f"/reset-password.html?token={quote(token)}"
    return f"{configured_base}{path}" if configured_base else path


def _include_reset_link_in_response() -> bool:
    return os.getenv("AUTH_INCLUDE_RESET_LINK_IN_RESPONSE", "").lower() in {"1", "true", "yes"}


def _append_reset_outbox(email: str, reset_url: str) -> None:
    outbox = _read_json(_reset_outbox_file(), [])
    outbox.append(
        {
            "email": email,
            "reset_url": reset_url,
            "created_at": _now().isoformat(),
        }
    )
    _write_json(_reset_outbox_file(), outbox)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest) -> dict[str, str]:
    email = _normalize_email(body.email)
    with _storage_lock:
        users = _read_json(_users_file(), [])
        if _find_user(users, email) is not None:
            raise HTTPException(status_code=409, detail="An account with that email already exists")
        users.append(
            {
                "email": email,
                "password_hash": _hash_password(body.password),
                "created_at": _now().isoformat(),
                "updated_at": _now().isoformat(),
            }
        )
        _write_json(_users_file(), users)
    return {"message": "User registered", "email": email}


@router.post("/login")
def login(body: LoginRequest) -> dict[str, str]:
    email = _normalize_email(body.email)
    with _storage_lock:
        user = _find_user(_read_json(_users_file(), []), email)
    if user is None or not _verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {"message": "Login successful", "email": email}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest) -> dict[str, str]:
    email = _normalize_email(body.email)
    response = {"message": GENERIC_RESET_MESSAGE}
    with _storage_lock:
        user = _find_user(_read_json(_users_file(), []), email)
        if user is None:
            return response

        token = secrets.token_urlsafe(32)
        reset_url = _reset_url(token)
        reset_tokens = _read_json(_reset_tokens_file(), [])
        reset_tokens.append(
            {
                "email": email,
                "token_hash": _hash_reset_token(token),
                "expires_at": (_now() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)).isoformat(),
                "used_at": "",
                "created_at": _now().isoformat(),
            }
        )
        _write_json(_reset_tokens_file(), reset_tokens)
        _append_reset_outbox(email, reset_url)

    if _include_reset_link_in_response():
        response["reset_url"] = reset_url
    return response


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest) -> dict[str, str]:
    token_hash = _hash_reset_token(body.token)
    with _storage_lock:
        users = _read_json(_users_file(), [])
        reset_tokens = _read_json(_reset_tokens_file(), [])
        reset_record = None
        for candidate in reset_tokens:
            if candidate.get("token_hash") == token_hash:
                reset_record = candidate
                break
        if reset_record is None or reset_record.get("used_at"):
            raise HTTPException(status_code=400, detail="Invalid or expired password reset token")
        try:
            expires_at = _parse_datetime(reset_record["expires_at"])
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=500, detail="Invalid password reset storage") from error
        if expires_at <= _now():
            raise HTTPException(status_code=400, detail="Invalid or expired password reset token")

        user = _find_user(users, reset_record.get("email", ""))
        if user is None:
            raise HTTPException(status_code=400, detail="Invalid or expired password reset token")

        user["password_hash"] = _hash_password(body.password)
        user["updated_at"] = _now().isoformat()
        for candidate in reset_tokens:
            if candidate.get("email") == user["email"] and not candidate.get("used_at"):
                candidate["used_at"] = _now().isoformat()
        _write_json(_users_file(), users)
        _write_json(_reset_tokens_file(), reset_tokens)

    return {"message": "Password has been reset"}
