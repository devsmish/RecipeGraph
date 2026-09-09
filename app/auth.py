"""Password hashing and token creation helpers.

Two different kinds of secrets are handled here, deliberately with different hashing
techniques:

- Passwords are user-chosen and often low-entropy (people reuse "password123"), so they
  need a slow, deliberately expensive hash (argon2id) to resist brute-force guessing.
- Refresh tokens are generated with cryptographically secure randomness, so they
  already have high entropy. Hashing them only needs to be fast and collision-resistant
  (SHA-256) — running argon2 on something already random would just waste CPU for no
  extra security.
"""

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from models import RefreshToken

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

_password_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_context.verify(password, password_hash)


def create_access_token(user_id: uuid.UUID) -> str:
    """Short-lived JWT — verified without a database lookup on every request."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def create_refresh_token(session: AsyncSession, user_id: uuid.UUID) -> str:
    """Generate a new refresh token, persist its hash, and return the raw token.

    The raw token is returned to the client exactly once and never stored — only its
    hash lives in the database, same principle as passwords: a leaked database alone
    isn't enough to impersonate a user by replaying their refresh token.

    Deliberately not a JWT: a JWT refresh token would be verifiable without a database
    lookup, which means it *can't* be revoked before it expires. An opaque token backed
    by a database row is what makes `logout` possible at all.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    session.add(RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at))

    return raw_token
