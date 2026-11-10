"""rateRecipe at the API level: upsert, aggregates and comments (v0.2.11).

Value-range validation and database-error mapping live in test_rate_recipe_validation.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select

from db import async_session_maker
from factories import access_token_for, create_rating, create_recipe, create_user
from models import Rating, RatingComment

RATING_FIELDS = "id value createdAt updatedAt comment { id text } user { username }"
RATE = f"mutation($input: RateRecipeInput!) {{ rateRecipe(input: $input) {{ {RATING_FIELDS} }} }}"
RECIPE_RATINGS = """
query($id: ID!) {
    recipe(id: $id) {
        avgRating ratingsCount
        ratings { value comment { text } user { username } }
    }
}
"""
AUTH_REQUIRED = "Authentication required"


def rate_input(recipe, value, **extra):
    return {"input": {"recipeId": str(recipe.id), "value": value, **extra}}


def messages(result) -> list[str]:
    assert "errors" in result, f"expected errors, got {result}"
    return [e["message"] for e in result["errors"]]


async def count(model) -> int:
    async with async_session_maker() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def recipe_ratings(gql, recipe):
    return (await gql(RECIPE_RATINGS, {"id": str(recipe.id)}))["data"]["recipe"]


# Creating and updating


async def test_first_rating_creates_a_row_for_the_caller(auth_gql, user):
    recipe = await create_recipe()

    result = await auth_gql(RATE, rate_input(recipe, 4))

    assert "errors" not in result
    rating = result["data"]["rateRecipe"]
    assert rating["value"] == 4
    assert rating["user"] == {"username": user.username}
    assert rating["comment"] is None
    assert rating["id"] and rating["createdAt"]
    assert await count(Rating) == 1


async def test_rating_again_updates_the_same_row_instead_of_adding_one(auth_gql):
    recipe = await create_recipe()
    first = (await auth_gql(RATE, rate_input(recipe, 4)))["data"]["rateRecipe"]

    second = (await auth_gql(RATE, rate_input(recipe, 2)))["data"]["rateRecipe"]

    assert second["id"] == first["id"]
    assert second["value"] == 2
    assert second["createdAt"] == first["createdAt"]
    assert datetime.fromisoformat(second["updatedAt"]) >= datetime.fromisoformat(first["updatedAt"])
    assert await count(Rating) == 1


async def test_an_existing_rating_made_elsewhere_is_updated_too(auth_gql, user):
    recipe = await create_recipe()
    seeded = await create_rating(recipe=recipe, user=user, value=1)

    result = await auth_gql(RATE, rate_input(recipe, 5))

    assert result["data"]["rateRecipe"]["id"] == str(seeded.id)
    assert result["data"]["rateRecipe"]["value"] == 5
    assert await count(Rating) == 1


async def test_the_same_user_can_rate_different_recipes_independently(auth_gql):
    soup, stew = await create_recipe(), await create_recipe()

    await auth_gql(RATE, rate_input(soup, 5))
    await auth_gql(RATE, rate_input(stew, 2))
    await auth_gql(RATE, rate_input(soup, 4))  # changing one must not touch the other

    assert await count(Rating) == 2
    assert (await recipe_ratings(auth_gql, soup))["avgRating"] == 4.0
    assert (await recipe_ratings(auth_gql, stew))["avgRating"] == 2.0


async def test_a_rejected_update_leaves_the_existing_rating_untouched(auth_gql):
    recipe = await create_recipe()
    await auth_gql(RATE, rate_input(recipe, 3, commentText="Fine"))

    result = await auth_gql(RATE, rate_input(recipe, 6, commentText="Changed my mind"))

    assert messages(result) == ["Rating value must be between 1 and 5"]
    stored = (await recipe_ratings(auth_gql, recipe))["ratings"]
    assert [(r["value"], r["comment"]["text"]) for r in stored] == [(3, "Fine")]


async def test_the_whole_scale_can_be_reached_by_updating(auth_gql):
    recipe = await create_recipe()

    for value in (1, 5, 1):
        result = await auth_gql(RATE, rate_input(recipe, value))
        assert result["data"]["rateRecipe"]["value"] == value

    assert await count(Rating) == 1


# Several users and the aggregates


async def test_two_users_rating_one_recipe_are_both_counted(gql):
    recipe = await create_recipe()
    anna, ben = await create_user(username="anna"), await create_user(username="ben")

    await gql(RATE, rate_input(recipe, 4), token=access_token_for(anna))
    await gql(RATE, rate_input(recipe, 5), token=access_token_for(ben))

    data = await recipe_ratings(gql, recipe)
    assert data["ratingsCount"] == 2
    assert data["avgRating"] == 4.5
    assert sorted((r["user"]["username"], r["value"]) for r in data["ratings"]) == [("anna", 4), ("ben", 5)]


async def test_changing_a_rating_changes_the_average_but_not_the_count(gql):
    recipe = await create_recipe()
    anna, ben = await create_user(), await create_user()
    await gql(RATE, rate_input(recipe, 4), token=access_token_for(anna))
    await gql(RATE, rate_input(recipe, 5), token=access_token_for(ben))

    await gql(RATE, rate_input(recipe, 2), token=access_token_for(anna))

    data = await recipe_ratings(gql, recipe)
    assert data["ratingsCount"] == 2
    assert data["avgRating"] == 3.5


async def test_a_recipe_nobody_rated_has_no_average(gql):
    recipe = await create_recipe()

    data = await recipe_ratings(gql, recipe)

    assert data["ratingsCount"] == 0
    assert data["avgRating"] is None


# Comments


async def test_a_comment_is_created_together_with_the_rating(auth_gql, gql):
    recipe = await create_recipe()

    result = await auth_gql(RATE, rate_input(recipe, 5, commentText="Loved it"))

    assert result["data"]["rateRecipe"]["comment"]["text"] == "Loved it"
    assert await count(RatingComment) == 1
    ratings = (await recipe_ratings(gql, recipe))["ratings"]
    assert [(r["value"], r["comment"]["text"]) for r in ratings] == [(5, "Loved it")]


async def test_a_later_comment_replaces_the_earlier_one_in_place(auth_gql):
    recipe = await create_recipe()
    first = (await auth_gql(RATE, rate_input(recipe, 4, commentText="Good")))["data"]["rateRecipe"]

    second = (await auth_gql(RATE, rate_input(recipe, 4, commentText="Even better the next day")))["data"][
        "rateRecipe"
    ]

    assert second["comment"]["text"] == "Even better the next day"
    assert second["comment"]["id"] == first["comment"]["id"]  # updated, not a second comment
    assert await count(RatingComment) == 1


async def test_a_comment_can_be_added_to_a_rating_that_had_none(auth_gql):
    recipe = await create_recipe()
    await auth_gql(RATE, rate_input(recipe, 3))

    result = await auth_gql(RATE, rate_input(recipe, 3, commentText="Added later"))

    assert result["data"]["rateRecipe"]["comment"]["text"] == "Added later"
    assert await count(Rating) == 1
    assert await count(RatingComment) == 1


async def test_a_comment_left_out_of_a_later_call_is_kept(auth_gql):
    recipe = await create_recipe()
    await auth_gql(RATE, rate_input(recipe, 4, commentText="Keep me"))

    result = await auth_gql(RATE, rate_input(recipe, 1))  # only the value changes

    rating = result["data"]["rateRecipe"]
    assert rating["value"] == 1
    assert rating["comment"]["text"] == "Keep me"


async def test_an_explicit_null_comment_also_leaves_it_unchanged(auth_gql):
    # There is no way to remove a comment through the API: null means "don't touch it", exactly
    # like leaving the field out. This test records that behavior.
    recipe = await create_recipe()
    await auth_gql(RATE, rate_input(recipe, 4, commentText="Keep me"))

    result = await auth_gql(RATE, rate_input(recipe, 4, commentText=None))

    assert result["data"]["rateRecipe"]["comment"]["text"] == "Keep me"


async def test_comments_belong_to_their_own_rating(gql):
    recipe = await create_recipe()
    anna, ben = await create_user(username="anna"), await create_user(username="ben")

    await gql(RATE, rate_input(recipe, 5, commentText="Anna's comment"), token=access_token_for(anna))
    await gql(RATE, rate_input(recipe, 2, commentText="Ben's comment"), token=access_token_for(ben))
    await gql(RATE, rate_input(recipe, 3, commentText="Anna revised"), token=access_token_for(anna))

    ratings = (await recipe_ratings(gql, recipe))["ratings"]
    assert sorted((r["user"]["username"], r["value"], r["comment"]["text"]) for r in ratings) == [
        ("anna", 3, "Anna revised"),
        ("ben", 2, "Ben's comment"),
    ]
    assert await count(RatingComment) == 2


# Errors


async def test_rating_an_unknown_recipe_is_reported_as_not_found(auth_gql, sentry_calls):
    result = await auth_gql(RATE, {"input": {"recipeId": str(uuid.uuid4()), "value": 4, "commentText": "x"}})

    assert messages(result) == ["Recipe not found"]
    assert await count(Rating) == 0
    assert await count(RatingComment) == 0
    assert sentry_calls == []


async def test_rating_requires_authentication(gql):
    recipe = await create_recipe()

    result = await gql(RATE, rate_input(recipe, 4))

    assert messages(result) == [AUTH_REQUIRED]
    assert await count(Rating) == 0


async def test_an_invalid_token_cannot_rate(gql):
    recipe = await create_recipe()

    result = await gql(RATE, rate_input(recipe, 4), token="not-a-real-token")

    assert messages(result) == [AUTH_REQUIRED]
    assert await count(Rating) == 0
