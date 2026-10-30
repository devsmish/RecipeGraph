"""Read side of the recipe API: recipe(id), myRecipes and the dictionary queries."""

import uuid

from factories import (
    access_token_for,
    create_ingredient,
    create_ingredient_category,
    create_rating,
    create_recipe,
    create_recipe_category,
    create_tag,
    create_user,
)
from models import MeasurementUnit

RECIPE = """
query($id: ID!) {
    recipe(id: $id) {
        id title description cookingTimeMinutes difficulty servings avgRating ratingsCount
        author { id username }
        category { id name }
        ingredients { amount unit ingredient { id name category { name } } }
        tags { name }
        ratings { value comment { text } user { username } }
    }
}
"""


def messages(result) -> list[str]:
    assert "errors" in result, f"expected errors, got {result}"
    return [e["message"] for e in result["errors"]]


# recipe(id)


async def test_recipe_returns_its_fields_and_every_nested_relation(gql, user):
    soups = await create_recipe_category(name="Soups")
    veg = await create_ingredient_category(name="Vegetables")
    dairy = await create_ingredient_category(name="Dairy")
    tomato = await create_ingredient(name="Tomato", category=veg)
    milk = await create_ingredient(name="Milk", category=dairy)
    vegan, quick = await create_tag(name="vegan"), await create_tag(name="quick")
    recipe = await create_recipe(
        author=user,
        category=soups,
        title="Tomato soup",
        description="Warm and simple",
        cooking_time_minutes=25,
        servings=4,
        ingredients=[(tomato, 500, MeasurementUnit.G), (milk, 0.5, MeasurementUnit.L)],
        tags=[vegan, quick],
    )
    reviewer, other_reviewer = await create_user(username="rev1"), await create_user(username="rev2")
    await create_rating(recipe=recipe, user=reviewer, value=4, comment="Tasty")
    await create_rating(recipe=recipe, user=other_reviewer, value=5)

    result = await gql(RECIPE, {"id": str(recipe.id)})

    assert "errors" not in result
    data = result["data"]["recipe"]
    assert data["id"] == str(recipe.id)
    assert data["title"] == "Tomato soup"
    assert data["description"] == "Warm and simple"
    assert data["cookingTimeMinutes"] == 25
    assert data["difficulty"] == "EASY"
    assert data["servings"] == 4
    assert data["author"] == {"id": str(user.id), "username": user.username}
    assert data["category"] == {"id": str(soups.id), "name": "Soups"}
    assert [
        (line["ingredient"]["name"], line["ingredient"]["category"]["name"], line["amount"], line["unit"])
        for line in data["ingredients"]
    ] == [("Tomato", "Vegetables", 500.0, "G"), ("Milk", "Dairy", 0.5, "L")]
    assert sorted(t["name"] for t in data["tags"]) == ["quick", "vegan"]
    assert sorted((r["user"]["username"], r["value"], (r["comment"] or {}).get("text")) for r in data["ratings"]) == [
        ("rev1", 4, "Tasty"),
        ("rev2", 5, None),
    ]
    assert data["ratingsCount"] == 2
    assert data["avgRating"] == 4.5


async def test_recipe_without_ingredients_tags_or_ratings_has_empty_collections(gql):
    recipe = await create_recipe(description=None)

    data = (await gql(RECIPE, {"id": str(recipe.id)}))["data"]["recipe"]

    assert data["description"] is None
    assert data["ingredients"] == []
    assert data["tags"] == []
    assert data["ratings"] == []
    assert data["ratingsCount"] == 0
    assert data["avgRating"] is None


async def test_recipe_is_readable_without_authentication(gql):
    recipe = await create_recipe(title="Public soup")

    result = await gql("query($id: ID!) { recipe(id: $id) { title } }", {"id": str(recipe.id)})

    assert result["data"]["recipe"]["title"] == "Public soup"


async def test_unknown_recipe_is_reported_as_not_found(gql, sentry_calls):
    result = await gql("query($id: ID!) { recipe(id: $id) { id } }", {"id": str(uuid.uuid4())})

    assert messages(result) == ["Recipe not found"]
    assert sentry_calls == []


# myRecipes


async def test_my_recipes_returns_only_the_callers_recipes(auth_gql, user):
    await create_recipe(author=user, title="Mine 1")
    await create_recipe(author=user, title="Mine 2")
    await create_recipe(author=await create_user(), title="Someone else's")

    result = await auth_gql("query { myRecipes { title author { username } } }")

    assert sorted(r["title"] for r in result["data"]["myRecipes"]) == ["Mine 1", "Mine 2"]
    assert {r["author"]["username"] for r in result["data"]["myRecipes"]} == {user.username}


async def test_my_recipes_is_empty_for_a_user_without_recipes(auth_gql):
    result = await auth_gql("query { myRecipes { id } }")

    assert result["data"]["myRecipes"] == []


async def test_my_recipes_requires_authentication(gql):
    await create_recipe()

    result = await gql("query { myRecipes { id } }")

    assert messages(result) == ["Authentication required"]


async def test_my_recipes_with_an_invalid_token_is_treated_as_anonymous(gql):
    result = await gql("query { myRecipes { id } }", token="not-a-real-token")

    assert messages(result) == ["Authentication required"]


# Dictionary queries


async def test_recipe_categories_are_sorted_by_name(gql):
    for name in ("Soups", "Appetizers", "Mains"):
        await create_recipe_category(name=name)

    result = await gql("query { recipeCategories { id name } }")

    assert [c["name"] for c in result["data"]["recipeCategories"]] == ["Appetizers", "Mains", "Soups"]
    assert all(c["id"] for c in result["data"]["recipeCategories"])


async def test_ingredient_categories_are_sorted_by_name(gql):
    for name in ("Vegetables", "Dairy", "Meat"):
        await create_ingredient_category(name=name)

    result = await gql("query { ingredientCategories { name } }")

    assert [c["name"] for c in result["data"]["ingredientCategories"]] == ["Dairy", "Meat", "Vegetables"]


async def test_dictionary_queries_are_empty_when_there_is_no_data(gql):
    result = await gql("query { recipeCategories { id } ingredientCategories { id } ingredients { id } }")

    assert result["data"] == {"recipeCategories": [], "ingredientCategories": [], "ingredients": []}


async def test_dictionary_queries_do_not_require_authentication(gql):
    await create_recipe_category(name="Soups")

    result = await gql("query { recipeCategories { name } }")

    assert "errors" not in result


async def test_ingredients_are_sorted_by_name_and_carry_their_category(gql):
    veg = await create_ingredient_category(name="Vegetables")
    for name in ("Tomato", "Basil", "Onion"):
        await create_ingredient(name=name, category=veg)

    result = await gql("query { ingredients { name category { name } } }")

    assert result["data"]["ingredients"] == [
        {"name": "Basil", "category": {"name": "Vegetables"}},
        {"name": "Onion", "category": {"name": "Vegetables"}},
        {"name": "Tomato", "category": {"name": "Vegetables"}},
    ]


async def test_ingredient_search_matches_a_substring_ignoring_case(gql):
    for name in ("Tomato", "Tomato paste", "Basil", "Cherry tomatoes"):
        await create_ingredient(name=name)

    for term in ("tom", "TOM", "Tom"):
        result = await gql("query($s: String) { ingredients(search: $s) { name } }", {"s": term})
        assert [i["name"] for i in result["data"]["ingredients"]] == ["Cherry tomatoes", "Tomato", "Tomato paste"]


async def test_ingredient_search_with_no_match_is_empty_and_an_empty_term_returns_everything(gql):
    for name in ("Tomato", "Basil"):
        await create_ingredient(name=name)

    no_match = await gql('query { ingredients(search: "zzz") { name } }')
    empty_term = await gql('query { ingredients(search: "") { name } }')
    no_term = await gql("query { ingredients { name } }")

    assert no_match["data"]["ingredients"] == []
    assert [i["name"] for i in empty_term["data"]["ingredients"]] == ["Basil", "Tomato"]
    assert [i["name"] for i in no_term["data"]["ingredients"]] == ["Basil", "Tomato"]


async def test_another_users_token_sees_the_same_dictionaries(gql):
    await create_recipe_category(name="Soups")
    someone = await create_user()

    anonymous = await gql("query { recipeCategories { name } }")
    authenticated = await gql("query { recipeCategories { name } }", token=access_token_for(someone))

    assert anonymous["data"] == authenticated["data"]
