"""GraphQL request context.

Extracts and verifies the caller's identity from the Authorization header once per
request, so individual resolvers can read `info.context["user"]` instead of each one
re-parsing and re-verifying the token itself.
"""

import uuid

import jwt
from fastapi import Request
from sqlalchemy import select

from auth import JWT_ALGORITHM, JWT_SECRET
from db import async_session_maker
from models import User as UserModel


class NotAuthenticatedError(Exception):
    def __init__(self) -> None:
        super().__init__("Authentication required")


async def _load_user_from_access_token(token: str) -> UserModel | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        # Expired, malformed, or tampered token — treated the same as "no token at all", so an
        # invalid token just means "proceed as an anonymous caller" rather than an error.
        return None

    if payload.get("type") != "access":
        # A refresh token (or anything else) presented where an access token is
        # expected — reject the same way as an invalid signature.
        return None

    async with async_session_maker() as session:
        result = await session.execute(
            select(UserModel).where(UserModel.id == uuid.UUID(payload["sub"]))
        )
        return result.scalar_one_or_none()


async def get_context(request: Request) -> dict:
    user_model = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
        user_model = await _load_user_from_access_token(token)

    return {"user": user_model}


def require_user(info) -> UserModel:
    """Fetch the authenticated user from context, or raise if there isn't one.

    Mutations that must not run anonymously (e.g. createRecipe, once it exists) should
    call this first:

        @strawberry.mutation
        async def create_recipe(self, info: strawberry.Info, input: ...) -> Recipe:
            user = require_user(info)
            ...
    """
    user = info.context["user"]
    if user is None:
        raise NotAuthenticatedError()
    return user
