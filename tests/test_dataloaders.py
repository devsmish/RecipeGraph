"""Tests for the per-request DataLoaders.

Two kinds of checks:
- the *effect*: a query for N recipes with every nested field fires the same number of
  SQL statements no matter what N is (no N+1);
- the *contract*: each batch function returns one result per key, in key order, and
  one-to-many loaders return an empty list (not a missing entry) for keys with no rows.
"""

import uuid
from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from sqlalchemy import event

from conftest import graphql_request
from db import async_session_maker, engine
from tests.factories import (
    access_token_for,
    create_ingredient,
    create_ingredient_category,
    create_rating,
    create_recipe,
    create_recipe_category,
    create_tag,
    create_user,
)
from models import Difficulty, Recipe, RecipeCategory, User

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


@dataclass
class Seeded:
    author: User
    categories: list[RecipeCategory]
    token: str


async def _seed(recipe_count: int) -> Seeded:
    """`recipe_count` fully populated recipes for one author, plus one bare recipe (no
    ingredients, tags or ratings). The token is the author's."""
    author = await create_user(username="author", email="author@example.com")
    raters = [await create_user(username=f"rater{i}", email=f"rater{i}@example.com") for i in range(3)]
    categories = [await create_recipe_category(name=f"Category {i}") for i in range(3)]
    ingredient_categories = [await create_ingredient_category(name=f"IngCat {i}") for i in range(2)]
    catalog = [
        await create_ingredient(name=f"Ingredient {i}", category=ingredient_categories[i % 2])
        for i in range(4)
    ]
    tags = [await create_tag(name=f"tag{i}") for i in range(3)]

    for i in range(recipe_count):
        recipe = await create_recipe(
            author=author,
            category=categories[i % 3],
            title=f"Recipe {i}",
            ingredients=[catalog[(i + position) % 4] for position in range(3)],
            tags=tags[: 1 + i % 3],
        )
        for rater in raters[: 1 + i % 3]:
            await create_rating(recipe=recipe, user=rater, value=4, comment="tasty")

    await create_recipe(
        author=author,
        category=categories[0],
        title="Bare recipe",
        cooking_time_minutes=5,
        difficulty=Difficulty.HARD,
        servings=1,
    )
    return Seeded(author=author, categories=categories, token=access_token_for(author))


async def _run_all_fields_query(client, token: str) -> tuple[dict, int]:
    with count_selects() as statements:
        result = await graphql_request(client, ALL_FIELDS_QUERY, token=token)
    assert "errors" not in result, result.get("errors")
    return result, len(statements)


async def test_query_count_does_not_grow_with_recipe_count(client):
    seeded = await _seed(recipe_count=3)
    token = seeded.token
    small_result, small_count = await _run_all_fields_query(client, token)
    assert len(small_result["data"]["myRecipes"]) == 4  # 3 + the bare one

    # Add 12 more recipes for the same author and ask for everything again.
    for i in range(12):
        await create_recipe(
            author=seeded.author,
            category=seeded.categories[0],
            title=f"Extra {i}",
            difficulty=Difficulty.MEDIUM,
        )

    large_result, large_count = await _run_all_fields_query(client, token)
    assert len(large_result["data"]["myRecipes"]) == 16

    print(f"\nSELECT count — 4 recipes: {small_count}, 16 recipes: {large_count}")
    assert large_count == small_count
    # O(field count): auth user + myRecipes + one batch per relation level. Generous
    # upper bound so adding a field doesn't make this brittle, but far below N+1 levels.
    assert large_count <= 12


async def test_nested_data_is_correct_including_empty_collections(client):
    seeded = await _seed(recipe_count=2)
    result, _ = await _run_all_fields_query(client, seeded.token)
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
