"""GraphQL schema: types, queries, and mutations."""

import strawberry
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from auth import create_access_token, create_refresh_token, hash_password, verify_password
from db import async_session_maker, engine
from models import User as UserModel


class UsernameOrEmailTakenError(Exception):
    def __init__(self) -> None:
        super().__init__("Username or email is already taken")


class InvalidCredentialsError(Exception):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


@strawberry.type(description="A registered user of RecipeGraph.")
class User:
    id: strawberry.ID
    username: str
    email: str

    @staticmethod
    def from_model(user: UserModel) -> "User":
        return User(id=strawberry.ID(str(user.id)), username=user.username, email=user.email)


@strawberry.type(description="Tokens issued after a successful registration or login.")
class AuthPayload:
    access_token: str = strawberry.field(
        description="Short-lived JWT — send this with every authenticated request."
    )
    refresh_token: str = strawberry.field(
        description="Long-lived opaque token — use only to obtain a new access token."
    )
    user: User


@strawberry.input(description="Fields required to create a new account.")
class RegisterInput:
    username: str
    email: str
    password: str


@strawberry.input(description="Credentials for logging into an existing account.")
class LoginInput:
    email: str
    password: str


@strawberry.type
class Query:
    @strawberry.field(description="Liveness check — does not touch any dependency.")
    def hello(self) -> str:
        return "RecipeGraph API is alive"

    @strawberry.field(description="Readiness check — verifies a real PostgreSQL connection.")
    async def health(self) -> str:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "postgres: ok"


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Create a new user account and return auth tokens.")
    async def register(self, input: RegisterInput) -> AuthPayload:
        async with async_session_maker() as session:
            user = UserModel(
                username=input.username,
                email=input.email,
                password_hash=hash_password(input.password),
            )
            session.add(user)

            try:
                # flush (not commit) sends the INSERT and assigns user.id, without
                # ending the transaction — lets catch the unique-constraint
                # violation and turn it into a clean GraphQL error instead of a raw
                # database exception.
                await session.flush()
            except IntegrityError as exc:
                await session.rollback()
                raise UsernameOrEmailTakenError() from exc

            access_token = create_access_token(user.id)
            refresh_token = await create_refresh_token(session, user.id)
            await session.commit()

        return AuthPayload(
            access_token=access_token,
            refresh_token=refresh_token,
            user=User.from_model(user),
        )

    @strawberry.mutation(description="Authenticate with email and password, return auth tokens.")
    async def login(self, input: LoginInput) -> AuthPayload:
        async with async_session_maker() as session:
            result = await session.execute(select(UserModel).where(UserModel.email == input.email))
            user = result.scalar_one_or_none()

            if user is None or not verify_password(input.password, user.password_hash):
                raise InvalidCredentialsError()

            access_token = create_access_token(user.id)
            refresh_token = await create_refresh_token(session, user.id)
            await session.commit()

        return AuthPayload(
            access_token=access_token,
            refresh_token=refresh_token,
            user=User.from_model(user),
        )


schema = strawberry.Schema(query=Query, mutation=Mutation)
