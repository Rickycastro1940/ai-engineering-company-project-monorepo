from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

if not hasattr(_bcrypt, "__about__"):
    # Passlib 1.7 reads this legacy bcrypt metadata during backend initialization.
    class _BcryptAbout:
        __version__ = getattr(_bcrypt, "__version__", "unknown")

    _bcrypt.__about__ = _BcryptAbout()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-development-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as error:
        raise credentials_error from error

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise credentials_error
    return subject
