from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

USERS_FILE = Path(os.getenv("AUTH_USERS_FILE", str(REPO_ROOT / "users.csv")))
RESETS_FILE = Path(os.getenv("AUTH_RESETS_FILE", str(REPO_ROOT / "password_resets.csv")))

USER_FIELDS = ["email", "password_hash"]
RESET_FIELDS = ["token", "email", "expires_at", "used"]

PBKDF2_ITERATIONS = 200_000
_lock = threading.Lock()


def _token_ttl_minutes() -> int:
    """Reset-token lifetime; read at call time so config changes are picked up."""
    try:
        return max(1, int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30")))
    except ValueError:
        return 30


# --- password hashing (stdlib PBKDF2, no external deps) ---------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, hash_b64 = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, base64.binascii.Error):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(candidate, expected)


# --- user store -------------------------------------------------------------


def _ensure_file(path: Path, fieldnames: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=fieldnames).writeheader()


def _load_users() -> list[dict[str, str]]:
    _ensure_file(USERS_FILE, USER_FIELDS)
    with USERS_FILE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _save_users(users: list[dict[str, str]]) -> None:
    with USERS_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=USER_FIELDS)
        writer.writeheader()
        for user in users:
            writer.writerow({"email": user["email"], "password_hash": user["password_hash"]})


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def find_user(email: str) -> dict[str, str] | None:
    target = _normalize_email(email)
    for user in _load_users():
        if _normalize_email(user.get("email", "")) == target:
            return user
    return None


def verify_credentials(email: str, password: str) -> bool:
    user = find_user(email)
    if user is None:
        return False
    return verify_password(password, user.get("password_hash", ""))


# --- reset tokens -----------------------------------------------------------


def _load_resets() -> list[dict[str, str]]:
    _ensure_file(RESETS_FILE, RESET_FIELDS)
    with RESETS_FILE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _save_resets(resets: list[dict[str, str]]) -> None:
    with RESETS_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESET_FIELDS)
        writer.writeheader()
        for row in resets:
            writer.writerow({field: row.get(field, "") for field in RESET_FIELDS})


def create_reset_token(email: str) -> str:
    """Issue a new reset token for an existing user. Caller must verify the user."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_token_ttl_minutes())
    with _lock:
        resets = _load_resets()
        resets.append(
            {
                "token": token,
                "email": _normalize_email(email),
                "expires_at": expires_at.isoformat(),
                "used": "0",
            }
        )
        _save_resets(resets)
    return token


def _is_expired(expires_at: str) -> bool:
    try:
        return datetime.now(timezone.utc) >= datetime.fromisoformat(expires_at)
    except ValueError:
        return True


def consume_reset_token(token: str, new_password: str) -> bool:
    """Validate a reset token, set the new password, and mark the token used.

    Returns False when the token is unknown, already used, or expired.
    """
    token = (token or "").strip()
    if not token or not new_password:
        return False
    with _lock:
        resets = _load_resets()
        entry = next((row for row in resets if row.get("token") == token), None)
        if entry is None or entry.get("used") == "1" or _is_expired(entry.get("expires_at", "")):
            return False

        users = _load_users()
        target = _normalize_email(entry.get("email", ""))
        user = next((u for u in users if _normalize_email(u.get("email", "")) == target), None)
        if user is None:
            return False

        user["password_hash"] = hash_password(new_password)
        _save_users(users)

        entry["used"] = "1"
        _save_resets(resets)
        return True
