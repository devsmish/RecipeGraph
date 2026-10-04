"""Tests for the per-request DataLoaders.

Two kinds of checks:
- the *effect*: a query for N recipes with every nested field fires the same number of
  SQL statements no matter what N is (no N+1);
- the *contract*: each batch function returns one result per key, in key order, and
  one-to-many loaders return an empty list (not a missing entry) for keys with no rows.
"""

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from auth import create_access_token
from conftest import graphql_request
from db import async_session_maker, engine
from models import (
    Difficulty,
    IngredientCatalog,
    IngredientCategory,
    MeasurementUnit,
    Rating,
    RatingComment,
    Recipe,
    RecipeCategory,
    RecipeIngredient,
    Tag,
    User,
    recipe_tags,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


ALL_FIELDS_QUERY = """
query {
    myRecipes {
        id
        title
        avgRating
        ratingsCount
        author { id username }
        category { id name }
        ingredients {
            amount
            unit
            ingredient { id name category { id name } }
        }
        tags { id name }
        ratings {
            value
            comment { text }
            user { id username }
        }
    }
}
"""


@contextmanager
def count_selects():
    """Count SELECT statements sent to PostgreSQL while the block runs."""
    statements: list[str] = []

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", on_execute)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", on_execute)


async def _seed(recipe_count: int) -> str:
    """Create `recipe_count` fully populated recipes for one author, plus one bare recipe
    (no ingredients, tags or ratings). Returns the author's access token."""
    async with async_session_maker() as session:
        author = User(username="author", email="author@example.com", password_hash="x")
        raters = [
            User(username=f"rater{i}", email=f"rater{i}@example.com", password_hash="x")
            for i in range(3)
        ]
        categories = [RecipeCategory(name=f"Category {i}") for i in range(3)]
        ing_categories = [IngredientCategory(name=f"IngCat {i}") for i in range(2)]
        session.add_all([author, *raters, *categories, *ing_categories])
        await session.flush()

        catalog = [
            IngredientCatalog(name=f"Ingredient {i}", category_id=ing_categories[i % 2].id)
            for i in range(4)
        ]
        tags = [Tag(name=f"tag{i}") for i in range(3)]
        session.add_all([*catalog, *tags])
        await session.flush()

        for i in range(recipe_count):
            recipe = Recipe(
                author_id=author.id,
                category_id=categories[i % 3].id,
                title=f"Recipe {i}",
                cooking_time_minutes=10,
                difficulty=Difficulty.EASY,
                servings=2,
            )
            session.add(recipe)
            await session.flush()

            for position in range(3):
                session.add(
                    RecipeIngredient(
                        recipe_id=recipe.id,
                        ingredient_id=catalog[(i + position) % 4].id,
                        amount=1,
                        unit=MeasurementUnit.G,
                        position=position,
                    )
                )
            for tag in tags[: 1 + i % 3]:
                await session.execute(recipe_tags.insert().values(recipe_id=recipe.id, tag_id=tag.id))
            for rater in raters[: 1 + i % 3]:
                rating = Rating(recipe_id=recipe.id, user_id=rater.id, value=4)
                session.add(rating)
                await session.flush()
                session.add(RatingComment(rating_id=rating.id, text="tasty"))

        session.add(
            Recipe(
                author_id=author.id,
                category_id=categories[0].id,
                title="Bare recipe",
                cooking_time_minutes=5,
                difficulty=Difficulty.HARD,
                servings=1,
            )
        )
        await session.commit()
        return create_access_token(author.id)


async def _run_all_fields_query(client, token: str) -> tuple[dict, int]:
    with count_selects() as statements:
        result = await graphql_request(client, ALL_FIELDS_QUERY, token=token)
    assert "errors" not in result, result.get("errors")
    return result, len(statements)


async def test_query_count_does_not_grow_with_recipe_count(client):
    token = await _seed(recipe_count=3)
    small_result, small_count = await _run_all_fields_query(client, token)
    assert len(small_result["data"]["myRecipes"]) == 4  # 3 + the bare one

    # Add 12 more recipes for the same author and ask for everything again.
    from sqlalchemy import select

    async with async_session_maker() as session:
        author = (await session.execute(select(User).where(User.username == "author"))).scalar_one()
        category = (await session.execute(select(RecipeCategory))).scalars().first()
        for i in range(12):
            session.add(
                Recipe(
                    author_id=author.id,
                    category_id=category.id,
                    title=f"Extra {i}",
                    cooking_time_minutes=10,
                    difficulty=Difficulty.MEDIUM,
                    servings=2,
                )
            )
        await session.commit()

    large_result, large_count = await _run_all_fields_query(client, token)
    assert len(large_result["data"]["myRecipes"]) == 16

    print(f"\nSELECT count — 4 recipes: {small_count}, 16 recipes: {large_count}")
    assert large_count == small_count
    # O(field count): auth user + myRecipes + one batch per relation level. Generous
    # upper bound so adding a field doesn't make this brittle, but far below N+1 levels.
    assert large_count <= 12


async def test_nested_data_is_correct_including_empty_collections(client):
    token = await _seed(recipe_count=2)
    result, _ = await _run_all_fields_query(client, token)
    recipes = {r["title"]: r for r in result["data"]["myRecipes"]}

    full = recipes["Recipe 1"]
    assert full["author"]["username"] == "author"
    assert full["category"]["name"] == "Category 1"
    assert [i["amount"] for i in full["ingredients"]] == [1.0, 1.0, 1.0]
    assert all(i["ingredient"]["category"]["name"].startswith("IngCat") for i in full["ingredients"])
    assert len(full["tags"]) == 2
    assert full["ratingsCount"] == 2 and full["avgRating"] == 4.0
    assert {r["user"]["username"] for r in full["ratings"]} == {"rater0", "rater1"}
    assert all(r["comment"]["text"] == "tasty" for r in full["ratings"])

    bare = recipes["Bare recipe"]
    assert bare["ingredients"] == []
    assert bare["tags"] == []
    assert bare["ratings"] == []
    assert bare["ratingsCount"] == 0
    assert bare["avgRating"] is None


async def test_loaders_return_results_in_key_order_with_empty_lists():
    from loaders import create_loaders

    await _seed(recipe_count=2)
    async with async_session_maker() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(Recipe).order_by(Recipe.title))).scalars().all()
    by_title = {r.title: r.id for r in rows}
    missing = uuid.uuid4()  # a recipe id with no rows anywhere

    # Deliberately not alphabetical, with an unknown key in the middle and a duplicate.
    keys = [by_title["Recipe 1"], missing, by_title["Bare recipe"], by_title["Recipe 0"], missing]

    loaders = create_loaders()
    for loader in (loaders.ingredients_by_recipe, loaders.tags_by_recipe, loaders.ratings_by_recipe):
        results = await loader.load_many(keys)
        assert len(results) == len(keys)
        assert results[1] == [] and results[4] == []  # unknown key -> empty list
        assert results[2] == []  # recipe that exists but has no children -> empty list
        assert len(results[0]) > 0 and len(results[3]) > 0

    # Order of results follows the order of keys (check via ids carried by each row).
    ing = await create_loaders().ingredients_by_recipe.load_many(keys)
    assert all(row.recipe_id == by_title["Recipe 1"] for row in ing[0])
    assert all(row.recipe_id == by_title["Recipe 0"] for row in ing[3])
    # Ingredient lines come back sorted by position.
    assert [row.position for row in ing[0]] == sorted(row.position for row in ing[0])


async def test_loaders_are_fresh_per_request():
    from loaders import create_loaders

    a, b = create_loaders(), create_loaders()
    assert a is not b
    assert a.user is not b.user
