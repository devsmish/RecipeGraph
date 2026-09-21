"""Tests for the data model / schema itself.

Complements test_db_connection.py (which tests connectivity and URL-encoding); this
file tests that the migrated schema actually behaves the way models.py says it should:
unique constraints, check constraints, and how enum values are actually stored.
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from db import async_session_maker
from models import (
    Difficulty,
    Rating,
    Recipe,
    RecipeCategory,
    User,
    IngredientCategory,
    IngredientCatalog,
    Tag,
    RatingComment)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_can_create_and_read_a_user():
    async with async_session_maker() as session:
        user = User(username="alice", email="alice@example.com", password_hash="hash")
        session.add(user)
        await session.commit()

        result = await session.execute(select(User).where(User.username == "alice"))
        fetched = result.scalar_one()
        assert fetched.email == "alice@example.com"


async def test_username_must_be_unique():
    async with async_session_maker() as session:
        session.add(User(username="bob", email="bob1@example.com", password_hash="x"))
        await session.commit()

        session.add(User(username="bob", email="bob2@example.com", password_hash="x"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_email_must_be_unique():
    async with async_session_maker() as session:
        session.add(User(username="carol1", email="dup@example.com", password_hash="x"))
        await session.commit()

        session.add(User(username="carol2", email="dup@example.com", password_hash="x"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_recipe_category_name_must_be_unique():
    async with async_session_maker() as session:
        session.add(RecipeCategory(name="Duplicate category"))
        await session.commit()

        session.add(RecipeCategory(name="Duplicate category"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_difficulty_enum_is_stored_lowercase():
    """Regression test: SQLAlchemy defaults to storing an enum member's *name*
    (e.g. "EASY") unless values_callable is set. models.py sets it explicitly via
    the _pg_enum() helper — this confirms the database actually stores "easy", not
    "EASY".
    """
    async with async_session_maker() as session:
        category = RecipeCategory(name="Enum test category")
        author = User(username="dave", email="dave@example.com", password_hash="x")
        session.add_all([category, author])
        await session.flush()

        recipe = Recipe(
            author_id=author.id,
            category_id=category.id,
            title="Enum test recipe",
            cooking_time_minutes=10,
            difficulty=Difficulty.EASY,
            servings=2,
        )
        session.add(recipe)
        await session.commit()
        recipe_id = recipe.id

        # Raw SQL, not the ORM — checking what's actually IN the database, not what
        # SQLAlchemy converts it back into on the way out.
        raw = await session.execute(
            text("SELECT difficulty::text FROM recipes WHERE id = :id"),
            {"id": recipe_id},
        )
        assert raw.scalar_one() == "easy"


async def _make_test_recipe(session, *, username: str, email: str) -> Recipe:
    """Shared setup for the rating tests below — a minimal valid recipe to rate."""
    category = RecipeCategory(name=f"Category for {username}")
    author = User(username=username, email=email, password_hash="x")
    session.add_all([category, author])
    await session.flush()

    recipe = Recipe(
        author_id=author.id,
        category_id=category.id,
        title=f"Recipe for {username}",
        cooking_time_minutes=10,
        difficulty=Difficulty.EASY,
        servings=2,
    )
    session.add(recipe)
    await session.flush()
    return recipe


async def test_one_rating_per_user_per_recipe():
    """UNIQUE(recipe_id, user_id) is what makes "changing a rating" an UPDATE,
    not a new row — this confirms the database actually enforces that.
    """
    async with async_session_maker() as session:
        recipe = await _make_test_recipe(session, username="erin", email="erin@example.com")
        rater = User(username="erin_rater", email="erin_rater@example.com", password_hash="x")
        session.add(rater)
        await session.flush()

        session.add(Rating(recipe_id=recipe.id, user_id=rater.id, value=5))
        await session.commit()

        session.add(Rating(recipe_id=recipe.id, user_id=rater.id, value=3))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_rating_value_must_be_between_one_and_five():
    async with async_session_maker() as session:
        recipe = await _make_test_recipe(session, username="frank", email="frank@example.com")
        rater = User(username="frank_rater", email="frank_rater@example.com", password_hash="x")
        session.add(rater)
        await session.flush()

        session.add(Rating(recipe_id=recipe.id, user_id=rater.id, value=6))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_ingredient_category_name_must_be_unique():
    """Validation of ingredient category name uniqueness (unique=True)."""
    async with async_session_maker() as session:
        session.add(IngredientCategory(name="Dairy"))
        await session.commit()

        session.add(IngredientCategory(name="Dairy"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_ingredient_catalog_name_must_be_unique():
    """Checking the uniqueness of the ingredient name in the reference list."""
    async with async_session_maker() as session:
        category = IngredientCategory(name="Vegetables")
        session.add(category)
        await session.flush()

        session.add(IngredientCatalog(category_id=category.id, name="Tomato"))
        await session.commit()

        session.add(IngredientCatalog(category_id=category.id, name="Tomato"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_tag_name_must_be_unique():
    """Tag uniqueness check."""
    async with async_session_maker() as session:
        session.add(Tag(name="vegan"))
        await session.commit()

        session.add(Tag(name="vegan"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_rating_comment_must_be_one_to_one():
    """Checking the 1:1 constraint for rating comments (unique=True on rating_id)."""
    async with async_session_maker() as session:
        recipe = await _make_test_recipe(session, username="commenter", email="commenter@example.com")
        rater = User(username="rater_usr", email="rater_usr@example.com", password_hash="x")
        session.add(rater)
        await session.flush()

        rating = Rating(recipe_id=recipe.id, user_id=rater.id, value=5)
        session.add(rating)
        await session.flush()

        # First comment — successful
        session.add(RatingComment(rating_id=rating.id, text="Great recipe!"))
        await session.commit()

        # Second comment on the same rating — should trigger an IntegrityError
        session.add(RatingComment(rating_id=rating.id, text="Second comment on same rating"))
        with pytest.raises(IntegrityError):
            await session.commit()
