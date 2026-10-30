"""Write side of the recipe API: createRecipe, updateRecipe, deleteRecipe."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from db import async_session_maker
from factories import (
    access_token_for,
    create_ingredient,
    create_rating,
    create_recipe,
    create_recipe_category,
    create_tag,
    create_user,
)
from models import (
    IngredientCatalog,
    Rating,
    RatingComment,
    Recipe,
    RecipeCategory,
    RecipeIngredient,
    Tag,
    User,
    recipe_tags,
)

RECIPE_FIELDS = """
    id title description cookingTimeMinutes difficulty servings
    author { username }
    category { id name }
    ingredients { amount unit ingredient { name } }
    tags { name }
"""
CREATE = f"mutation($input: CreateRecipeInput!) {{ createRecipe(input: $input) {{ {RECIPE_FIELDS} }} }}"
UPDATE = f"mutation($id: ID!, $input: UpdateRecipeInput!) {{ updateRecipe(id: $id, input: $input) {{ {RECIPE_FIELDS} }} }}"
DELETE = "mutation($id: ID!) { deleteRecipe(id: $id) }"
READ = f"query($id: ID!) {{ recipe(id: $id) {{ {RECIPE_FIELDS} }} }}"

NOT_OWNER = "You can only modify your own recipes"
AUTH_REQUIRED = "Authentication required"


def messages(result) -> list[str]:
    assert "errors" in result, f"expected errors, got {result}"
    return [e["message"] for e in result["errors"]]


async def count(model_or_table) -> int:
    async with async_session_maker() as session:
        return (await session.execute(select(func.count()).select_from(model_or_table))).scalar_one()


def create_input(category, ingredient_lines=(), **overrides):
    base = {
        "categoryId": str(category.id),
        "title": "Tomato soup",
        "cookingTimeMinutes": 25,
        "difficulty": "MEDIUM",
        "servings": 4,
        "ingredients": [
            {"ingredientId": str(ing.id), "amount": amount, "unit": unit} for ing, amount, unit in ingredient_lines
        ],
    }
    base.update(overrides)
    return base


# createRecipe


async def test_create_recipe_with_ingredients_and_tags(auth_gql, gql, user):
    soups = await create_recipe_category(name="Soups")
    tomato, milk = await create_ingredient(name="Tomato"), await create_ingredient(name="Milk")
    vegan, quick = await create_tag(name="vegan"), await create_tag(name="quick")

    result = await auth_gql(
        CREATE,
        {
            "input": create_input(
                soups,
                [(tomato, 500, "G"), (milk, 0.5, "L")],
                description="Warm and simple",
                tagIds=[str(vegan.id), str(quick.id)],
            )
        },
    )

    assert "errors" not in result
    created = result["data"]["createRecipe"]
    assert created["title"] == "Tomato soup"
    assert created["description"] == "Warm and simple"
    assert created["cookingTimeMinutes"] == 25
    assert created["difficulty"] == "MEDIUM"
    assert created["servings"] == 4
    assert created["author"] == {"username": user.username}  # the caller, not something the client chooses
    assert created["category"]["name"] == "Soups"
    assert [(i["ingredient"]["name"], i["amount"], i["unit"]) for i in created["ingredients"]] == [
        ("Tomato", 500.0, "G"),
        ("Milk", 0.5, "L"),
    ]
    assert sorted(t["name"] for t in created["tags"]) == ["quick", "vegan"]

    # ... and it was really stored, not just echoed back.
    stored = (await gql(READ, {"id": created["id"]}))["data"]["recipe"]
    assert stored == created


async def test_create_recipe_without_optional_fields(auth_gql):
    soups = await create_recipe_category()

    result = await auth_gql(CREATE, {"input": create_input(soups)})

    created = result["data"]["createRecipe"]
    assert created["description"] is None
    assert created["ingredients"] == []
    assert created["tags"] == []


async def test_create_recipe_requires_authentication(gql):
    category = await create_recipe_category()

    result = await gql(CREATE, {"input": create_input(category)})

    assert messages(result) == [AUTH_REQUIRED]
    assert await count(Recipe) == 0


async def test_create_recipe_with_an_unknown_category(auth_gql, sentry_calls):
    unknown = SimpleNamespace(id=uuid.uuid4())  # well-formed, but nothing has this id

    result = await auth_gql(CREATE, {"input": create_input(unknown)})

    assert messages(result) == ["Recipe category not found"]
    assert await count(Recipe) == 0
    assert sentry_calls == []  # a client mistake, not a server bug


async def test_create_recipe_with_an_unknown_ingredient_writes_nothing(auth_gql, sentry_calls):
    category = await create_recipe_category()
    known = await create_ingredient()
    unknown = SimpleNamespace(id=uuid.uuid4())  # well-formed, but nothing has this id

    result = await auth_gql(CREATE, {"input": create_input(category, [(known, 1, "G"), (unknown, 1, "G")])})

    assert messages(result) == ["Ingredient not found"]
    assert await count(Recipe) == 0
    assert await count(RecipeIngredient) == 0
    assert sentry_calls == []


async def test_create_recipe_with_an_unknown_tag_writes_nothing(auth_gql, sentry_calls):
    category = await create_recipe_category()
    known_tag = await create_tag()

    result = await auth_gql(CREATE, {"input": create_input(category, tagIds=[str(known_tag.id), str(uuid.uuid4())])})

    assert messages(result) == ["Tag not found"]
    assert await count(Recipe) == 0
    assert await count(recipe_tags) == 0
    assert sentry_calls == []


async def test_create_recipe_with_a_tag_listed_twice_attaches_it_once(auth_gql):
    category = await create_recipe_category()
    tag = await create_tag(name="vegan")

    result = await auth_gql(CREATE, {"input": create_input(category, tagIds=[str(tag.id), str(tag.id)])})

    assert "errors" not in result
    assert [t["name"] for t in result["data"]["createRecipe"]["tags"]] == ["vegan"]


async def test_create_recipe_may_list_the_same_ingredient_on_two_lines(auth_gql):
    category = await create_recipe_category()
    salt = await create_ingredient(name="Salt")

    result = await auth_gql(CREATE, {"input": create_input(category, [(salt, 1, "TBSP"), (salt, 5, "G")])})

    lines = result["data"]["createRecipe"]["ingredients"]
    assert [(line["ingredient"]["name"], line["amount"], line["unit"]) for line in lines] == [
        ("Salt", 1.0, "TBSP"),
        ("Salt", 5.0, "G"),
    ]


# updateRecipe


async def test_partial_update_changes_only_the_given_fields(auth_gql, user):
    category = await create_recipe_category(name="Soups")
    salt, tag = await create_ingredient(name="Salt"), await create_tag(name="vegan")
    recipe = await create_recipe(
        author=user, category=category, title="Old title", description="Keep me", ingredients=[salt], tags=[tag]
    )

    result = await auth_gql(UPDATE, {"id": str(recipe.id), "input": {"title": "New title"}})

    updated = result["data"]["updateRecipe"]
    assert updated["title"] == "New title"
    assert updated["description"] == "Keep me"
    assert updated["cookingTimeMinutes"] == 10
    assert updated["difficulty"] == "EASY"
    assert updated["servings"] == 2
    assert updated["category"]["name"] == "Soups"
    assert [i["ingredient"]["name"] for i in updated["ingredients"]] == ["Salt"]
    assert [t["name"] for t in updated["tags"]] == ["vegan"]


async def test_update_can_change_every_scalar_field_and_the_category(auth_gql, user):
    recipe = await create_recipe(author=user)
    mains = await create_recipe_category(name="Mains")

    result = await auth_gql(
        UPDATE,
        {
            "id": str(recipe.id),
            "input": {
                "categoryId": str(mains.id),
                "title": "Stew",
                "description": "Hearty",
                "cookingTimeMinutes": 90,
                "difficulty": "HARD",
                "servings": 6,
            },
        },
    )

    updated = result["data"]["updateRecipe"]
    assert (updated["title"], updated["description"], updated["cookingTimeMinutes"]) == ("Stew", "Hearty", 90)
    assert (updated["difficulty"], updated["servings"], updated["category"]["name"]) == ("HARD", 6, "Mains")


async def test_description_left_out_is_unchanged_but_explicit_null_clears_it(auth_gql, user):
    recipe = await create_recipe(author=user, description="Original")

    left_out = await auth_gql(UPDATE, {"id": str(recipe.id), "input": {"title": "Other"}})
    assert left_out["data"]["updateRecipe"]["description"] == "Original"

    cleared = await auth_gql(UPDATE, {"id": str(recipe.id), "input": {"description": None}})
    assert cleared["data"]["updateRecipe"]["description"] is None
    assert cleared["data"]["updateRecipe"]["title"] == "Other"  # untouched by the second call


async def test_ingredients_and_tags_are_replaced_not_merged(auth_gql, user):
    old_ingredient, new_a, new_b = [await create_ingredient(name=n) for n in ("Old", "NewA", "NewB")]
    old_tag, new_tag = await create_tag(name="old"), await create_tag(name="new")
    recipe = await create_recipe(author=user, ingredients=[old_ingredient], tags=[old_tag])

    result = await auth_gql(
        UPDATE,
        {
            "id": str(recipe.id),
            "input": {
                "ingredients": [
                    {"ingredientId": str(new_b.id), "amount": 2, "unit": "KG"},
                    {"ingredientId": str(new_a.id), "amount": 3, "unit": "G"},
                ],
                "tagIds": [str(new_tag.id)],
            },
        },
    )

    updated = result["data"]["updateRecipe"]
    assert [(i["ingredient"]["name"], i["amount"], i["unit"]) for i in updated["ingredients"]] == [
        ("NewB", 2.0, "KG"),
        ("NewA", 3.0, "G"),
    ]
    assert [t["name"] for t in updated["tags"]] == ["new"]


async def test_an_empty_tag_list_removes_all_tags(auth_gql, user):
    recipe = await create_recipe(author=user, tags=[await create_tag(), await create_tag()])

    result = await auth_gql(UPDATE, {"id": str(recipe.id), "input": {"tagIds": []}})

    assert result["data"]["updateRecipe"]["tags"] == []
    assert await count(recipe_tags) == 0


async def test_only_the_author_can_update(gql, user, sentry_calls):
    recipe = await create_recipe(author=user, title="Original")
    intruder = await create_user()

    result = await gql(
        UPDATE, {"id": str(recipe.id), "input": {"title": "Hijacked"}}, token=access_token_for(intruder)
    )

    assert messages(result) == [NOT_OWNER]
    stored = (await gql(READ, {"id": str(recipe.id)}))["data"]["recipe"]
    assert stored["title"] == "Original"
    assert sentry_calls == []


async def test_update_of_an_unknown_recipe(auth_gql, sentry_calls):
    result = await auth_gql(UPDATE, {"id": str(uuid.uuid4()), "input": {"title": "x"}})

    assert messages(result) == ["Recipe not found"]
    assert sentry_calls == []


async def test_update_requires_authentication(gql, user):
    recipe = await create_recipe(author=user)

    result = await gql(UPDATE, {"id": str(recipe.id), "input": {"title": "x"}})

    assert messages(result) == [AUTH_REQUIRED]


@pytest.mark.parametrize(
    "field, build_value, expected_message",
    [
        pytest.param("categoryId", lambda: str(uuid.uuid4()), "Recipe category not found", id="category"),
        pytest.param(
            "ingredients",
            lambda: [{"ingredientId": str(uuid.uuid4()), "amount": 1, "unit": "G"}],
            "Ingredient not found",
            id="ingredient",
        ),
        pytest.param("tagIds", lambda: [str(uuid.uuid4())], "Tag not found", id="tag"),
    ],
)
async def test_update_with_an_unknown_reference_changes_nothing(
    auth_gql, user, sentry_calls, field, build_value, expected_message
):
    recipe = await create_recipe(author=user, title="Original", ingredients=[await create_ingredient(name="Salt")])

    # The valid title in the same call must not be applied either: the update is all-or-nothing.
    result = await auth_gql(UPDATE, {"id": str(recipe.id), "input": {"title": "Changed", field: build_value()}})

    assert messages(result) == [expected_message]
    stored = (await auth_gql(READ, {"id": str(recipe.id)}))["data"]["recipe"]
    assert stored["title"] == "Original"
    assert [i["ingredient"]["name"] for i in stored["ingredients"]] == ["Salt"]
    assert sentry_calls == []


# deleteRecipe


async def test_the_author_can_delete_a_recipe(auth_gql, gql, user):
    recipe = await create_recipe(author=user)

    result = await auth_gql(DELETE, {"id": str(recipe.id)})

    assert result["data"]["deleteRecipe"] is True
    assert messages(await gql(READ, {"id": str(recipe.id)})) == ["Recipe not found"]


async def test_only_the_author_can_delete(gql, user, sentry_calls):
    recipe = await create_recipe(author=user)
    intruder = await create_user()

    result = await gql(DELETE, {"id": str(recipe.id)}, token=access_token_for(intruder))

    assert messages(result) == [NOT_OWNER]
    assert await count(Recipe) == 1
    assert sentry_calls == []


async def test_deleting_twice_is_not_an_error(auth_gql, user):
    recipe = await create_recipe(author=user)

    first = await auth_gql(DELETE, {"id": str(recipe.id)})
    second = await auth_gql(DELETE, {"id": str(recipe.id)})

    assert first["data"]["deleteRecipe"] is True
    assert second["data"]["deleteRecipe"] is False
    assert "errors" not in second


async def test_deleting_an_unknown_recipe_returns_false(auth_gql):
    result = await auth_gql(DELETE, {"id": str(uuid.uuid4())})

    assert result["data"]["deleteRecipe"] is False


async def test_delete_requires_authentication(gql, user):
    recipe = await create_recipe(author=user)

    result = await gql(DELETE, {"id": str(recipe.id)})

    assert messages(result) == [AUTH_REQUIRED]
    assert await count(Recipe) == 1


async def test_deleting_a_recipe_removes_its_dependent_rows_but_not_shared_data(auth_gql, user):
    category = await create_recipe_category()
    ingredients = [await create_ingredient(), await create_ingredient()]
    tags = [await create_tag(), await create_tag()]
    recipe = await create_recipe(author=user, category=category, ingredients=ingredients, tags=tags)
    await create_rating(recipe=recipe, value=5, comment="Great")
    await create_rating(recipe=recipe, value=3)
    survivor = await create_recipe(author=user, ingredients=ingredients[:1], tags=tags[:1])
    await create_rating(recipe=survivor, value=4, comment="Fine")

    result = await auth_gql(DELETE, {"id": str(recipe.id)})

    assert result["data"]["deleteRecipe"] is True
    # Gone with the recipe: its ingredient lines, tag links, ratings and rating comments ...
    assert await count(RecipeIngredient) == 1  # only the survivor's line
    assert await count(recipe_tags) == 1
    assert await count(Rating) == 1
    assert await count(RatingComment) == 1
    # ... while the shared dictionaries and users stay.
    assert await count(IngredientCatalog) == 2
    assert await count(Tag) == 2
    assert await count(RecipeCategory) == 2  # the one passed in + the survivor's own
    assert await count(User) >= 3
    assert await count(Recipe) == 1
