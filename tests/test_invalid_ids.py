"""End-to-end tests: malformed IDs sent to recipe operations (v0.2.7).

A malformed ID is the client's mistake: it must get a clear message naming the field,
must not be reported to Sentry, and must be rejected before anything is written.
"""

import uuid

import pytest
from sqlalchemy import func, select

from db import async_session_maker
from models import Recipe

ZERO_UUID = "00000000-0000-0000-0000-000000000000"  # well-formed, but nothing has this id


def invalid(field: str) -> str:
    return f'Invalid ID for "{field}": expected a UUID'


CREATE = """
mutation Create($input: CreateRecipeInput!) { createRecipe(input: $input) { id } }
"""
UPDATE = """
mutation Update($id: ID!, $input: UpdateRecipeInput!) { updateRecipe(id: $id, input: $input) { id } }
"""


def create_input(**overrides):
    base = {
        "categoryId": str(uuid.uuid4()),
        "title": "Soup",
        "cookingTimeMinutes": 10,
        "difficulty": "EASY",
        "servings": 2,
        "ingredients": [{"ingredientId": str(uuid.uuid4()), "amount": 1.0, "unit": "G"}],
        "tagIds": [],
    }
    base.update(overrides)
    return base


def two_ingredients_second_bad():
    return [
        {"ingredientId": str(uuid.uuid4()), "amount": 1.0, "unit": "G"},
        {"ingredientId": "oops", "amount": 2.0, "unit": "KG"},
    ]


CASES = [
    pytest.param(
        "query($id: ID!) { recipe(id: $id) { id } }",
        {"id": "abc"},
        invalid("id"),
        id="recipe(id)",
    ),
    pytest.param(
        CREATE,
        {"input": create_input(categoryId="abc")},
        invalid("categoryId"),
        id="createRecipe.categoryId",
    ),
    pytest.param(
        CREATE,
        {"input": create_input(ingredients=two_ingredients_second_bad())},
        invalid("ingredients[1].ingredientId"),
        id="createRecipe.ingredients[].ingredientId",
    ),
    pytest.param(
        CREATE,
        {"input": create_input(tagIds=[str(uuid.uuid4()), "nope"])},
        invalid("tagIds[1]"),
        id="createRecipe.tagIds",
    ),
    pytest.param(
        UPDATE,
        {"id": "abc", "input": {"title": "New"}},
        invalid("id"),
        id="updateRecipe.id",
    ),
    pytest.param(
        UPDATE,
        {"id": ZERO_UUID, "input": {"categoryId": "abc"}},
        invalid("categoryId"),
        id="updateRecipe.categoryId",
    ),
    pytest.param(
        UPDATE,
        {"id": ZERO_UUID, "input": {"ingredients": two_ingredients_second_bad()}},
        invalid("ingredients[1].ingredientId"),
        id="updateRecipe.ingredients[].ingredientId",
    ),
    pytest.param(
        UPDATE,
        {"id": ZERO_UUID, "input": {"tagIds": ["nope"]}},
        invalid("tagIds[0]"),
        id="updateRecipe.tagIds",
    ),
    pytest.param(
        "mutation($id: ID!) { deleteRecipe(id: $id) }",
        {"id": "abc"},
        invalid("id"),
        id="deleteRecipe.id",
    ),
    pytest.param(
        "mutation($input: RateRecipeInput!) { rateRecipe(input: $input) { value } }",
        {"input": {"recipeId": "abc", "value": 5}},
        invalid("recipeId"),
        id="rateRecipe.recipeId",
    ),
]


@pytest.mark.parametrize("query, variables, expected_message", CASES)
async def test_malformed_id_returns_a_clear_message(
    auth_gql, sentry_calls, query, variables, expected_message
):
    result = await auth_gql(query, variables)

    assert [e["message"] for e in result["errors"]] == [expected_message]
    assert "Internal server error" not in str(result)
    assert sentry_calls == []  # a client mistake, not a server bug


async def test_create_recipe_with_a_bad_ingredient_id_writes_nothing(auth_gql, sentry_calls):
    result = await auth_gql(CREATE, {"input": create_input(ingredients=two_ingredients_second_bad())})

    assert result["errors"][0]["message"] == invalid("ingredients[1].ingredientId")
    async with async_session_maker() as session:
        assert (await session.execute(select(func.count()).select_from(Recipe))).scalar_one() == 0


async def test_malformed_id_message_does_not_echo_the_value(auth_gql, sentry_calls):
    result = await auth_gql("query($id: ID!) { recipe(id: $id) { id } }", {"id": "<script>alert(1)</script>"})

    assert "script" not in str(result)


async def test_well_formed_but_unknown_ids_behave_as_before(auth_gql, sentry_calls):
    unknown_recipe = await auth_gql("query($id: ID!) { recipe(id: $id) { id } }", {"id": ZERO_UUID})
    assert unknown_recipe["errors"][0]["message"] == "Recipe not found"

    rate_unknown = await auth_gql("mutation($input: RateRecipeInput!) { rateRecipe(input: $input) { value } }",
        {"input": {"recipeId": ZERO_UUID, "value": 5}})
    assert rate_unknown["errors"][0]["message"] == "Recipe not found"

    delete_unknown = await auth_gql("mutation($id: ID!) { deleteRecipe(id: $id) }", {"id": ZERO_UUID})
    assert delete_unknown["data"]["deleteRecipe"] is False
    assert sentry_calls == []


async def test_uppercase_and_hyphenless_ids_are_accepted(auth_gql, sentry_calls):
    for form in (ZERO_UUID.upper(), ZERO_UUID.replace("-", "")):
        result = await auth_gql("query($id: ID!) { recipe(id: $id) { id } }", {"id": form})
        assert result["errors"][0]["message"] == "Recipe not found"
