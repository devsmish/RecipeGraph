"""Tests for GraphQL error handling (error_handling.py / errors.py)."""

import pytest
import strawberry

import error_handling
from error_handling import ErrorLoggingExtension
from errors import PublicError


class DemoPublicError(PublicError):
    def __init__(self) -> None:
        super().__init__("Safe message for the client")


@strawberry.type
class DemoQuery:
    @strawberry.field
    def public_failure(self) -> str | None:
        raise DemoPublicError()

    @strawberry.field
    def unexpected_failure(self) -> str | None:
        raise RuntimeError("SELECT * FROM users WHERE password_hash = 'secret' failed")

    @strawberry.field
    def fine(self) -> str:
        return "ok"


# Failing fields are nullable on purpose: a failing non-null field would null out its whole
# parent and graphql-core would stop reporting the sibling errors.
# A small schema of our own, so these tests don't depend on the database or on which
# resolvers happen to exist — only on the extension's behaviour.
demo_schema = strawberry.Schema(query=DemoQuery, extensions=[ErrorLoggingExtension])


def _messages(result) -> list[str]:
    """Messages of all errors in a result (and fail clearly if there are none)."""
    assert result.errors is not None, "expected the query to produce errors"
    return [e.message for e in result.errors]


@pytest.fixture
def sentry_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(error_handling, "capture_exception", calls.append)
    return calls


def test_public_error_message_reaches_the_client_and_is_not_sent_to_sentry(sentry_calls):
    result = demo_schema.execute_sync("{ publicFailure }")

    assert _messages(result) == ["Safe message for the client"]
    assert sentry_calls == []


def test_unexpected_error_is_masked_and_reported_to_sentry(sentry_calls):
    result = demo_schema.execute_sync("{ unexpectedFailure }")

    assert _messages(result) == ["Internal server error"]
    assert "SELECT" not in _messages(result)[0]
    assert result.errors is not None
    assert result.errors[0].path == ["unexpectedFailure"]  # still tells the client which field failed
    assert len(sentry_calls) == 1
    assert isinstance(sentry_calls[0], RuntimeError)


def test_graphql_validation_errors_pass_through_untouched(sentry_calls):
    # An unknown field is the client's mistake, not a server bug: the real message
    # ("Cannot query field ...") helps them, and nothing goes to Sentry.
    result = demo_schema.execute_sync("{ doesNotExist }")

    assert len(_messages(result)) == 1
    assert "doesNotExist" in _messages(result)[0]
    assert _messages(result)[0] != "Internal server error"
    assert sentry_calls == []


def test_syntax_errors_pass_through_untouched(sentry_calls):
    result = demo_schema.execute_sync("{ fine ")

    assert len(_messages(result)) == 1
    assert _messages(result)[0] != "Internal server error"
    assert sentry_calls == []


def test_successful_query_is_unaffected(sentry_calls):
    result = demo_schema.execute_sync("{ fine }")

    assert result.errors is None
    assert result.data == {"fine": "ok"}


def test_one_failing_field_does_not_hide_or_alter_the_others(sentry_calls):
    result = demo_schema.execute_sync("{ fine publicFailure unexpectedFailure }")

    assert result.data == {"fine": "ok", "publicFailure": None, "unexpectedFailure": None}
    assert sorted(_messages(result)) == [
        "Internal server error",
        "Safe message for the client",
    ]
    assert len(sentry_calls) == 1


def test_every_client_facing_error_is_a_public_error():
    # If one of these stops deriving from PublicError, its message silently becomes
    # "Internal server error" for clients (and noise in Sentry). New client-visible
    # errors should be added here.
    from context import NotAuthenticatedError
    from recipes import InvalidRatingValueError, NotRecipeOwnerError, RecipeNotFoundError
    from schema import InvalidCredentialsError, InvalidRefreshTokenError, UsernameOrEmailTakenError

    for error_class in (
        NotAuthenticatedError,
        InvalidRatingValueError,
        NotRecipeOwnerError,
        RecipeNotFoundError,
        InvalidCredentialsError,
        InvalidRefreshTokenError,
        UsernameOrEmailTakenError,
    ):
        assert issubclass(error_class, PublicError), error_class


def test_real_schema_has_the_error_extension_installed():
    # The extension used to exist but was never attached to the schema, so nothing was
    # actually being masked. This guards against that regressing.
    from schema import schema

    assert ErrorLoggingExtension in schema.extensions


async def test_real_api_keeps_public_errors_and_masks_unexpected_ones(client, monkeypatch):
    from conftest import graphql_request

    # Public: asking for a recipe that doesn't exist -> the real message comes through.
    missing = await graphql_request(
        client, 'query { recipe(id: "00000000-0000-0000-0000-000000000000") { id } }'
    )
    assert missing["errors"][0]["message"] == "Recipe not found"

    # Unexpected: make the database layer blow up with a message full of "internals".
    def broken_session_maker():
        raise RuntimeError("connection to server at db:5432 failed, password=hunter2")

    monkeypatch.setattr("recipes.async_session_maker", broken_session_maker)
    broken = await graphql_request(client, "query { recipeCategories { id } }")

    assert [e["message"] for e in broken["errors"]] == ["Internal server error"]
    assert "hunter2" not in str(broken)
