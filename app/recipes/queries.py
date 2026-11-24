"""GraphQL query fields for recipes and their dictionaries.

`RecipeQuery` is a base class of the root `Query` type (schema.py): Strawberry merges its fields
into `Query`, so clients see them as ordinary top-level queries.
"""

import strawberry

from context import require_user
from recipes import service
from recipes.types import Ingredient, IngredientCategory, Recipe, RecipeCategory


@strawberry.type
class RecipeQuery:
    @strawberry.field(description="A single recipe by id.")
    async def recipe(self, id: strawberry.ID) -> Recipe:
        return await service.resolve_recipe(id)

    @strawberry.field(description="Recipes belonging to the currently authenticated user.")
    async def my_recipes(self, info: strawberry.Info) -> list[Recipe]:
        user = require_user(info)
        return await service.resolve_my_recipes(user.id)

    @strawberry.field(description="All recipe categories (e.g. Salads, Soups) — one per recipe.")
    async def recipe_categories(self) -> list[RecipeCategory]:
        return await service.resolve_recipe_categories()

    @strawberry.field(description="All ingredient categories (e.g. Meat, Vegetables).")
    async def ingredient_categories(self) -> list[IngredientCategory]:
        return await service.resolve_ingredient_categories()

    @strawberry.field(description="Ingredient master list, optionally filtered by name.")
    async def ingredients(self, search: str | None = None) -> list[Ingredient]:
        return await service.resolve_ingredients(search)
