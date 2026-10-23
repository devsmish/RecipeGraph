"""rateRecipe: rating value validation and database error mapping (v0.2.8).

The value range is validated in the resolver, before any database work. The CHECK constraint
stays as a safety net, and only the integrity errors we can explain to the client are mapped
to client-facing errors; everything else must surface as an unexpected error.
"""

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import error_handling
import recipes
from auth import create_access_token
from conftest import graphql_request
from db import async_session_maker, engine
from models import Difficulty, Rating, Recipe, RecipeCategory, User

RATE = "mutation($input: RateRecipeInput!) { rateRecipe(input: $input) { value } }"
RANGE_MESSAGE = "Rating value must be between 1 and 5"


@pytest.fixture
async def setup():
    """A recipe by one user and a second user (the rater) with an access token."""
    async with async_session_maker() as session:
        author = User(username="author", email="author@example.com", password_hash="x")
        rater = User(username="rater", email="rater@example.com", password_hash="x")
        category = RecipeCategory(name="Soups")
        session.add_all([author, rater, category])
        await session.flush()
        recipe = Recipe(
            author_id=author.id,
            category_id=category.id,
            title="Soup",
            cooking_time_minutes=10,
            difficulty=Difficulty.EASY,
            servings=2,
        )
        session.add(recipe)
        await session.commit()
        return {
            "recipe_id": str(recipe.id),
            "rater_id": rater.id,
            "token": create_access_token(rater.id),
        }


@pytest.fixture
def sentry_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(error_handling, "capture_exception", calls.append)
    return calls


@contextmanager
def recorded_statements():
    statements: list[str] = []

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", on_execute)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", on_execute)


@pytest.fixture
def after_rating_lookup(monkeypatch):
    """Run an async action right after the resolver's lookup of the existing rating.

    That is the window between "the recipe exists and I have no rating yet" and the INSERT,
    i.e. where another request can change the database underneath the resolver.
    """
    actions = []
    original_execute = AsyncSession.execute

    async def execute(self, statement, *args, **kwargs):
        result = await original_execute(self, statement, *args, **kwargs)
        if actions and "FROM ratings" in str(statement):
            await actions.pop()()  # popped first, so the action's own queries don't re-trigger it
        return result

    monkeypatch.setattr(AsyncSession, "execute", execute)
    return actions.append


async def count_ratings() -> int:
    async with async_session_maker() as session:
        return (await session.execute(select(func.count()).select_from(Rating))).scalar_one()


@pytest.mark.parametrize("value", [0, 6, -1, 100, -100])
async def test_out_of_range_value_is_rejected_before_any_database_work(client, setup, sentry_calls, value):
    with recorded_statements() as statements:
        result = await graphql_request(
            client, RATE, {"input": {"recipeId": setup["recipe_id"], "value": value}}, token=setup["token"]
        )

    assert [e["message"] for e in result["errors"]] == [RANGE_MESSAGE]
    # Only the authentication lookup (users) ran; the resolver never touched recipes or ratings.
    assert not [s for s in statements if "recipes" in s or "ratings" in s]
    assert await count_ratings() == 0
    assert sentry_calls == []


@pytest.mark.parametrize("value", [1, 5])
async def test_boundary_values_are_accepted(client, setup, sentry_calls, value):
    result = await graphql_request(
        client, RATE, {"input": {"recipeId": setup["recipe_id"], "value": value}}, token=setup["token"]
    )

    assert "errors" not in result
    assert result["data"]["rateRecipe"]["value"] == value
    assert sentry_calls == []


async def test_check_constraint_violation_is_still_reported_as_an_invalid_value(
    client, setup, sentry_calls, monkeypatch
):
    # Widen the resolver's own range so 6 gets past it and reaches the database, whose CHECK
    # constraint (1..5) is the safety net.
    monkeypatch.setattr(recipes, "MAX_RATING_VALUE", 10)

    result = await graphql_request(
        client, RATE, {"input": {"recipeId": setup["recipe_id"], "value": 6}}, token=setup["token"]
    )

    assert [e["message"] for e in result["errors"]] == [RANGE_MESSAGE]
    assert await count_ratings() == 0
    assert sentry_calls == []


async def test_recipe_deleted_after_the_lookup_is_reported_as_not_found(
    client, setup, sentry_calls, after_rating_lookup
):
    async def delete_the_recipe():
        async with async_session_maker() as session:
            await session.execute(delete(Recipe).where(Recipe.id == uuid.UUID(setup["recipe_id"])))
            await session.commit()

    after_rating_lookup(delete_the_recipe)

    result = await graphql_request(
        client, RATE, {"input": {"recipeId": setup["recipe_id"], "value": 4}}, token=setup["token"]
    )

    # A foreign key violation used to be reported as an invalid rating value.
    assert [e["message"] for e in result["errors"]] == ["Recipe not found"]
    assert sentry_calls == []


async def test_other_integrity_errors_are_not_mislabelled_as_an_invalid_rating(
    client, setup, sentry_calls, after_rating_lookup
):
    # A concurrent first rating by the same user: our INSERT then violates UNIQUE(recipe_id,
    # user_id). That is not the client's mistake, so it must not become "Rating value must be ...".
    async def concurrent_first_rating():
        async with async_session_maker() as session:
            session.add(Rating(recipe_id=uuid.UUID(setup["recipe_id"]), user_id=setup["rater_id"], value=2))
            await session.commit()

    after_rating_lookup(concurrent_first_rating)

    result = await graphql_request(
        client, RATE, {"input": {"recipeId": setup["recipe_id"], "value": 4}}, token=setup["token"]
    )

    assert [e["message"] for e in result["errors"]] == ["Internal server error"]
    assert RANGE_MESSAGE not in str(result)
    assert len(sentry_calls) == 1  # treated as an unexpected error: reported, not swallowed
    assert type(sentry_calls[0]).__name__ == "IntegrityError"
