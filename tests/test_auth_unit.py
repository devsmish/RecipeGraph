import uuid
import jwt
from auth import (
    JWT_ALGORITHM,
    JWT_SECRET,
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from db import async_session_maker
from models import User


async def test_password_hashing_and_verification():
    raw_password = "TestSecret1234!"
    hashed = hash_password(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("SuperPass1234!", hashed) is False


def test_create_access_token_validity():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)

    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert "exp" in payload


async def test_create_and_hash_refresh_token():
    async with async_session_maker() as session:
        user = User(username="refresher", email="refresher@example.com", password_hash="x")
        session.add(user)
        await session.flush()

        raw_token = await create_refresh_token(session, user.id)
        await session.commit()

        assert isinstance(raw_token, str)
        assert len(raw_token) > 20
        assert hash_refresh_token(raw_token) == hash_refresh_token(raw_token)
