from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from auth import create_access_token, decode_access_token, hash_password, oauth2_scheme, verify_password
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field, field_validator
from services.database import AUTH_DB_PATH
from tinydb import Query, TinyDB
from tinydb.table import Document

REPO_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = AUTH_DB_PATH

UNSET = object()
router = APIRouter(tags=["users"])


class UserRole(str, Enum):
    admin = "admin"
    manager = "manager"
    user = "user"


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8)
    name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    address: Optional[str] = Field(default=None, max_length=240)

    @field_validator("name", "phone", "address", mode="before")
    @classmethod
    def blank_optional_as_none(cls, value: object) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return str(value)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: Optional[str] = Field(default=None, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: Optional[str] = Field(default=None, min_length=8)
    name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    address: Optional[str] = Field(default=None, max_length=240)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    role: Optional[UserRole] = None

    @field_validator("name", "phone", "address", mode="before")
    @classmethod
    def blank_optional_as_none(cls, value: object) -> Optional[str]:
        return UserCreate.blank_optional_as_none(value)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    address: Optional[str] = Field(default=None, max_length=240)

    @field_validator("name", "phone", "address", mode="before")
    @classmethod
    def blank_optional_as_none(cls, value: object) -> Optional[str]:
        return UserCreate.blank_optional_as_none(value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8)


class UserPublic(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    is_active: bool
    is_admin: bool
    role: str
    created_at: str


class ProfilePublic(BaseModel):
    id: int
    user_id: int
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(TokenResponse):
    user: UserPublic


def _auth_db() -> TinyDB:
    from services import database as dual_db

    dual_db.AUTH_DB_PATH = Path(DATABASE_PATH)
    try:
        return dual_db.get_auth_db()
    except OSError as error:
        raise HTTPException(status_code=503, detail="User store is unavailable.") from error


def _users_table():
    return _auth_db().table("users")


def _profiles_table():
    return _auth_db().table("profiles")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_role(role: str | UserRole | None, *, is_admin: bool | None = None) -> str:
    if is_admin is True:
        return UserRole.admin.value
    if isinstance(role, UserRole):
        return role.value
    if role in {item.value for item in UserRole}:
        return str(role)
    if is_admin is False:
        return UserRole.user.value
    return UserRole.user.value


def _document_to_user(document: Document | dict[str, Any] | None, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if document is None:
        return None
    user_id = int(document.doc_id) if isinstance(document, Document) else int(document["id"])
    payload = dict(document)
    role = _normalize_role(payload.get("role"), is_admin=bool(payload.get("is_admin", False)))
    if profile is None:
        profile = _get_profile_row(user_id) or {}
    return {
        "id": user_id,
        "email": payload["email"],
        "hashed_password": payload["hashed_password"],
        "is_active": bool(payload.get("is_active", True)),
        "role": role,
        "is_admin": role == UserRole.admin.value,
        "created_at": payload["created_at"],
        "name": profile.get("name"),
        "phone": profile.get("phone"),
        "address": profile.get("address"),
        "profile_id": profile.get("id"),
    }


def _get_profile_row(user_id: int) -> dict[str, Any] | None:
    UserQuery = Query()
    row = _profiles_table().get(UserQuery.user_id == user_id)
    if row is None:
        return None
    return {
        "id": int(row.doc_id) if isinstance(row, Document) else int(row.get("id", user_id)),
        "user_id": user_id,
        "name": row.get("name"),
        "phone": row.get("phone"),
        "address": row.get("address"),
    }


def _upsert_profile(user_id: int, *, name: Any = UNSET, phone: Any = UNSET, address: Any = UNSET) -> dict[str, Any]:
    existing = _get_profile_row(user_id)
    payload = {
        "user_id": user_id,
        "name": None if name is UNSET else name,
        "phone": None if phone is UNSET else phone,
        "address": None if address is UNSET else address,
    }
    if existing is not None:
        if name is UNSET:
            payload["name"] = existing.get("name")
        if phone is UNSET:
            payload["phone"] = existing.get("phone")
        if address is UNSET:
            payload["address"] = existing.get("address")
        _profiles_table().update(payload, doc_ids=[existing["id"]])
        return _get_profile_row(user_id) or payload
    profile_id = _profiles_table().insert(payload)
    payload["id"] = profile_id
    return payload


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user.get("name"),
        "phone": user.get("phone"),
        "address": user.get("address"),
        "is_active": user["is_active"],
        "is_admin": user["is_admin"],
        "role": user.get("role", UserRole.user.value),
        "created_at": user["created_at"],
    }


def _public_profile(user: dict[str, Any]) -> dict[str, Any]:
    profile = _get_profile_row(user["id"]) or _upsert_profile(user["id"])
    return {
        "id": profile.get("id", user["id"]),
        "user_id": user["id"],
        "name": profile.get("name"),
        "phone": profile.get("phone"),
        "address": profile.get("address"),
    }


def count_users() -> int:
    return len(_users_table())


def ensure_seed_supervisor() -> dict[str, Any]:
    existing = get_user_by_email("felipe.guerrero@brasaland.test")
    if existing is not None:
        return existing
    return create_user(
        "felipe.guerrero@brasaland.test",
        "brasaland-ops",
        is_admin=count_users() == 0,
        name="Felipe Guerrero",
        phone="+57 300 000 0000",
        address="Medellín HQ",
    )


def create_user(
    email: str,
    password: str,
    *,
    is_active: bool = True,
    is_admin: bool = False,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    role: str | UserRole | None = None,
) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    if get_user_by_email(normalized_email) is not None:
        raise HTTPException(status_code=409, detail="User with this email already exists")

    assigned_role = UserRole.admin.value if is_admin else _normalize_role(role)
    user_id = _users_table().insert(
        {
            "email": normalized_email,
            "hashed_password": hash_password(password),
            "is_active": is_active,
            "role": assigned_role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _upsert_profile(user_id, name=name, phone=phone, address=address)
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=500, detail="User was not created")
    return user


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    document = _users_table().get(doc_id=user_id)
    return _document_to_user(document)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    UserQuery = Query()
    document = _users_table().get(UserQuery.email == _normalize_email(email))
    return _document_to_user(document)


def list_users() -> list[dict[str, Any]]:
    users = [_document_to_user(document) for document in _users_table().all()]
    return sorted((user for user in users if user is not None), key=lambda item: item["id"])


def update_user(
    user_id: int,
    *,
    email: str | None = None,
    password: str | None = None,
    name: Any = UNSET,
    phone: Any = UNSET,
    address: Any = UNSET,
    is_active: bool | None = None,
    is_admin: bool | None = None,
    role: str | UserRole | None = None,
) -> dict[str, Any]:
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    updates: dict[str, Any] = {}
    if email is not None:
        normalized = _normalize_email(email)
        existing = get_user_by_email(normalized)
        if existing is not None and existing["id"] != user_id:
            raise HTTPException(status_code=409, detail="User with this email already exists")
        updates["email"] = normalized
    if password is not None:
        updates["hashed_password"] = hash_password(password)
    if is_active is not None:
        updates["is_active"] = is_active
    if role is not None or is_admin is not None:
        updates["role"] = _normalize_role(role if role is not None else user.get("role"), is_admin=is_admin)

    if updates:
        _users_table().update(updates, doc_ids=[user_id])
    if name is not UNSET or phone is not UNSET or address is not UNSET:
        _upsert_profile(user_id, name=name, phone=phone, address=address)

    updated = get_user_by_id(user_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return updated


def delete_user(user_id: int) -> dict[str, Any]:
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    profile = _get_profile_row(user_id)
    _users_table().remove(doc_ids=[user_id])
    if profile is not None:
        _profiles_table().remove(doc_ids=[profile["id"]])
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


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest) -> dict[str, Any]:
    user = authenticate_user(body.email, body.password)
    if user is None or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _build_auth_response(user)


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
def register_and_login(body: UserCreate) -> dict[str, Any]:
    user = create_user(
        body.email,
        body.password,
        is_admin=count_users() == 0,
        name=body.name,
        phone=body.phone,
        address=body.address,
    )
    return _build_auth_response(user)


@router.get("/auth/me", response_model=UserPublic)
def read_current_user(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return _public_user(current_user)


@router.get("/profiles/me", response_model=ProfilePublic)
def read_my_profile(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return _public_profile(current_user)


@router.put("/profiles/me", response_model=UserPublic)
def update_my_profile(
    body: ProfileUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user = update_user(
        current_user["id"],
        name=body.name if "name" in body.model_fields_set else UNSET,
        phone=body.phone if "phone" in body.model_fields_set else UNSET,
        address=body.address if "address" in body.model_fields_set else UNSET,
    )
    return _public_user(user)


@router.post("/users", response_model=UserPublic, status_code=201)
def register_user(body: UserCreate) -> dict[str, Any]:
    return _public_user(
        create_user(
            body.email,
            body.password,
            is_admin=count_users() == 0,
            name=body.name,
            phone=body.phone,
            address=body.address,
        )
    )


@router.get("/users", response_model=list[UserPublic])
def read_users(current_user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    return [_public_user(user) for user in list_users()]


@router.get("/users/{user_id}", response_model=UserPublic)
def read_user(user_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return _public_user(user)


@router.put("/users/{user_id}", response_model=UserPublic)
def replace_user(user_id: int, body: UserUpdate, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    if not current_user["is_admin"] and (
        body.is_active is not None or body.is_admin is not None or body.role is not None
    ):
        raise HTTPException(status_code=403, detail="Only an admin can update user status or role")
    user = update_user(
        user_id,
        email=body.email,
        password=body.password,
        name=body.name if "name" in body.model_fields_set else UNSET,
        phone=body.phone if "phone" in body.model_fields_set else UNSET,
        address=body.address if "address" in body.model_fields_set else UNSET,
        is_active=body.is_active if current_user["is_admin"] else None,
        is_admin=body.is_admin if current_user["is_admin"] else None,
        role=body.role if current_user["is_admin"] else None,
    )
    return _public_user(user)


@router.delete("/users/{user_id}", response_model=UserPublic)
def remove_user(user_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    return _public_user(delete_user(user_id))
