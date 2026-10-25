"""Tests for the shared test factories and fixtures (factories.py, conftest.py)."""

from sqlalchemy import func, select

from db import async_session_maker
from tests.factories import (
    access_token_for,
    create_ingredient,
    create_rating,
    create_recipe,
    create_tag,
    create_user,
)
from models import (
    MeasurementUnit,
    RatingComment,
    Recipe,
    RecipeIngredient,
    recipe_tags,
)


async def test_unique_defaults_never_collide():
    users = [await create_user() for _ in range(3)]
    ingredients = [await create_ingredient() for _ in range(3)]
    tags = [await create_tag() for _ in range(3)]

    assert len({u.username for u in users}) == 3
    assert len({u.email for u in users}) == 3
    assert len({i.name for i in ingredients}) == 3
    assert len({t.name for t in tags}) == 3


async def test_create_recipe_with_no_arguments_is_complete_and_valid():
    recipe = await create_recipe()

    async with async_session_maker() as session:
        stored = (await session.execute(select(Recipe).where(Recipe.id == recipe.id))).scalar_one()
    assert stored.title
    assert stored.author_id and stored.category_id


async def test_create_recipe_keeps_ingredient_order_amounts_and_units():
    salt, flour, milk = await create_ingredient(), await create_ingredient(), await create_ingredient()

    recipe = await create_recipe(
        ingredients=[salt, (flour, 250, MeasurementUnit.G), (milk, 0.5, MeasurementUnit.L)]
    )

    async with async_session_maker() as session:
        rows = (
            await session.execute(
                select(RecipeIngredient)
                .where(RecipeIngredient.recipe_id == recipe.id)
                .order_by(RecipeIngredient.position)
            )
        ).scalars().all()
    assert [r.ingredient_id for r in rows] == [salt.id, flour.id, milk.id]
    assert [r.position for r in rows] == [0, 1, 2]
    assert [float(r.amount) for r in rows] == [1.0, 250.0, 0.5]
    assert [r.unit for r in rows] == [MeasurementUnit.G, MeasurementUnit.G, MeasurementUnit.L]


async def test_create_recipe_attaches_tags():
    vegan, quick = await create_tag(), await create_tag()

    recipe = await create_recipe(tags=[vegan, quick])

    async with async_session_maker() as session:
        tag_ids = (
            await session.execute(select(recipe_tags.c.tag_id).where(recipe_tags.c.recipe_id == recipe.id))
        ).scalars().all()
    assert sorted(tag_ids) == sorted([vegan.id, quick.id])


async def test_create_rating_creates_its_own_recipe_and_user_and_an_optional_comment():
    plain = await create_rating(value=3)
    commented = await create_rating(value=5, comment="Great!")

    assert plain.recipe_id != commented.recipe_id
    async with async_session_maker() as session:
        comments = (await session.execute(select(func.count()).select_from(RatingComment))).scalar_one()
        text = (await session.execute(select(RatingComment.text))).scalar_one()
    assert comments == 1
    assert text == "Great!"


async def test_access_token_for_authenticates_as_that_user(gql):
    someone = await create_user(username="someone", email="someone@example.com")

    result = await gql("query { currentUser { username } }", token=access_token_for(someone))

    assert result["data"]["currentUser"] == {"username": "someone"}


async def test_gql_without_a_token_is_anonymous(gql):
    result = await gql("query { currentUser { username } }")

    assert result["data"]["currentUser"] is None


async def test_auth_gql_is_authenticated_as_the_user_fixture(auth_gql, user):
    result = await auth_gql("query { currentUser { username email } }")

    assert result["data"]["currentUser"] == {"username": user.username, "email": user.email}
