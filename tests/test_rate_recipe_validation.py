"""rateRecipe: rating value validation and database error mapping (v0.2.8).

The value range is validated in the resolver, before any database work. The CHECK constraint
stays as a safety net, and only the integrity errors we can explain to the client are mapped
to client-facing errors; everything else must surface as an unexpected error.
"""

from contextlib import contextmanager

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import recipes
from db import async_session_maker, engine
from tests.factories import create_recipe
from models import Rating, Recipe

RATE = "mutation($input: RateRecipeInput!) { rateRecipe(input: $input) { value } }"
RANGE_MESSAGE = "Rating value must be between 1 and 5"


@pytest.fixture
async def recipe():
    """A recipe by some other user; the `user` fixture is the one who rates it."""
    return await create_recipe()


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
async def test_out_of_range_value_is_rejected_before_any_database_work(auth_gql, recipe, sentry_calls, value):
    with recorded_statements() as statements:
        result = await auth_gql(RATE, {"input": {"recipeId": str(recipe.id), "value": value}})

    assert [e["message"] for e in result["errors"]] == [RANGE_MESSAGE]
    # Only the authentication lookup (users) ran; the resolver never touched recipes or ratings.
    assert not [s for s in statements if "recipes" in s or "ratings" in s]
    assert await count_ratings() == 0
    assert sentry_calls == []


@pytest.mark.parametrize("value", [1, 5])
async def test_boundary_values_are_accepted(auth_gql, recipe, sentry_calls, value):
    result = await auth_gql(RATE, {"input": {"recipeId": str(recipe.id), "value": value}})

    assert "errors" not in result
    assert result["data"]["rateRecipe"]["value"] == value
    assert sentry_calls == []


async def test_check_constraint_violation_is_still_reported_as_an_invalid_value(
    auth_gql, recipe, sentry_calls, monkeypatch
):
    # Widen the resolver's own range so 6 gets past it and reaches the database, whose CHECK
    # constraint (1..5) is the safety net.
    monkeypatch.setattr(recipes, "MAX_RATING_VALUE", 10)

    result = await auth_gql(RATE, {"input": {"recipeId": str(recipe.id), "value": 6}})

    assert [e["message"] for e in result["errors"]] == [RANGE_MESSAGE]
    assert await count_ratings() == 0
    assert sentry_calls == []


async def test_recipe_deleted_after_the_lookup_is_reported_as_not_found(
    auth_gql, recipe, sentry_calls, after_rating_lookup
):
    async def delete_the_recipe():
        async with async_session_maker() as session:
            await session.execute(delete(Recipe).where(Recipe.id == recipe.id))
            await session.commit()

    after_rating_lookup(delete_the_recipe)

    result = await auth_gql(RATE, {"input": {"recipeId": str(recipe.id), "value": 4}})

    # A foreign key violation used to be reported as an invalid rating value.
    assert [e["message"] for e in result["errors"]] == ["Recipe not found"]
    assert sentry_calls == []


async def test_other_integrity_errors_are_not_mislabelled_as_an_invalid_rating(
    auth_gql, recipe, user, sentry_calls, after_rating_lookup
):
    # A concurrent first rating by the same user: our INSERT then violates UNIQUE(recipe_id,
    # user_id). That is not the client's mistake, so it must not become "Rating value must be ...".
    async def concurrent_first_rating():
        async with async_session_maker() as session:
            session.add(Rating(recipe_id=recipe.id, user_id=user.id, value=2))
            await session.commit()

    after_rating_lookup(concurrent_first_rating)

    result = await auth_gql(RATE, {"input": {"recipeId": str(recipe.id), "value": 4}})

    assert [e["message"] for e in result["errors"]] == ["Internal server error"]
    assert RANGE_MESSAGE not in str(result)
    assert len(sentry_calls) == 1  # treated as an unexpected error: reported, not swallowed
    assert type(sentry_calls[0]).__name__ == "IntegrityError"
