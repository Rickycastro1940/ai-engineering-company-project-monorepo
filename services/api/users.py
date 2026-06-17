from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auth import create_access_token, decode_access_token, hash_password, oauth2_scheme, verify_password
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = REPO_ROOT / "data" / "company_api.db"

router = APIRouter(tags=["users"])


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None
    is_admin: bool | None = None


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8)


class UserPublic(BaseModel):
    id: int
    email: str
    is_active: bool
    is_admin: bool
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(TokenResponse):
    user: UserPublic


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_user_table() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    user = dict(row)
    user["is_active"] = bool(user["is_active"])
    user["is_admin"] = bool(user["is_admin"])
    return user


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "is_active": user["is_active"],
        "is_admin": user["is_admin"],
        "created_at": user["created_at"],
    }


def count_users() -> int:
    _ensure_user_table()
    with _connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    return int(row["count"])


def create_user(email: str, password: str, *, is_active: bool = True, is_admin: bool = False) -> dict[str, Any]:
    _ensure_user_table()
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with _connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (email, hashed_password, is_active, is_admin, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_normalize_email(email), hash_password(password), int(is_active), int(is_admin), created_at),
            )
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="User with this email already exists") from error

    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=500, detail="User was not created")
    return user


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    _ensure_user_table()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(row)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    _ensure_user_table()
    with _connect() as connection:
        row = connection.execute("SELECT * FROM users WHERE email = ?", (_normalize_email(email),)).fetchone()
    return _row_to_dict(row)


def list_users() -> list[dict[str, Any]]:
    _ensure_user_table()
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [_row_to_dict(row) for row in rows if row is not None]


def update_user(
    user_id: int,
    *,
    email: str | None = None,
    password: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
) -> dict[str, Any]:
    _ensure_user_table()
    updates: list[str] = []
    values: list[Any] = []
    if email is not None:
        updates.append("email = ?")
        values.append(_normalize_email(email))
    if password is not None:
        updates.append("hashed_password = ?")
        values.append(hash_password(password))
    if is_active is not None:
        updates.append("is_active = ?")
        values.append(int(is_active))
    if is_admin is not None:
        updates.append("is_admin = ?")
        values.append(int(is_admin))

    if not updates:
        user = get_user_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        return user

    values.append(user_id)
    try:
        with _connect() as connection:
            cursor = connection.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="User with this email already exists") from error

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


def delete_user(user_id: int) -> dict[str, Any]:
    _ensure_user_table()
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    with _connect() as connection:
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return user


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_email(email)
    if user is None or not verify_password(password, str(user["hashed_password"])):
        return None
    return user


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    subject = decode_access_token(token)
    try:
        user_id = int(subject)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials") from error

    user = get_user_by_id(user_id)
    if user is None or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive or missing user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _require_self_or_admin(user_id: int, current_user: dict[str, Any]) -> None:
    if current_user["id"] != user_id and not current_user["is_admin"]:
        raise HTTPException(status_code=403, detail="Not enough permissions")


def _build_auth_response(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "access_token": create_access_token(str(user["id"])),
        "token_type": "bearer",
        "user": _public_user(user),
    }


@router.post("/auth/token", response_model=TokenResponse)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()) -> dict[str, str]:
    user = authenticate_user(form_data.username, form_data.password)
    if user is None or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": create_access_token(str(user["id"])), "token_type": "bearer"}


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest) -> dict[str, str]:
    user = authenticate_user(body.email, body.password)
    if user is None or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": create_access_token(str(user["id"])), "token_type": "bearer"}


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register_and_login(body: UserCreate) -> dict[str, Any]:
    user = create_user(body.email, body.password, is_admin=count_users() == 0)
    return _build_auth_response(user)


@router.get("/auth/me", response_model=UserPublic)
def read_current_user(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return _public_user(current_user)


@router.post("/users", response_model=UserPublic, status_code=201)
def register_user(body: UserCreate) -> dict[str, Any]:
    return _public_user(create_user(body.email, body.password, is_admin=count_users() == 0))


@router.get("/users", response_model=list[UserPublic])
def read_users(current_user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [_public_user(user) for user in list_users()]


@router.get("/users/{user_id}", response_model=UserPublic)
def read_user(user_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return _public_user(user)


@router.put("/users/{user_id}", response_model=UserPublic)
def replace_user(user_id: int, body: UserUpdate, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    if not current_user["is_admin"] and (body.is_active is not None or body.is_admin is not None):
        raise HTTPException(status_code=403, detail="Only an admin can update user status or role")
    user = update_user(
        user_id,
        email=body.email,
        password=body.password,
        is_active=body.is_active if current_user["is_admin"] else None,
        is_admin=body.is_admin if current_user["is_admin"] else None,
    )
    return _public_user(user)


@router.delete("/users/{user_id}", response_model=UserPublic)
def remove_user(user_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    return _public_user(delete_user(user_id))
