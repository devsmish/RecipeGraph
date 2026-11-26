"""GraphQL mutation fields for recipes and ratings.

`RecipeMutation` is a base class of the root `Mutation` type (schema.py), like `RecipeQuery`.
Each field only checks authentication and calls the service layer.
"""

import strawberry

from context import require_user
from recipes import ratings, service
from recipes.inputs import CreateRecipeInput, RateRecipeInput, UpdateRecipeInput
from recipes.types import Rating, Recipe


@strawberry.type
class RecipeMutation:
    @strawberry.mutation(description="Create a new recipe. Requires authentication.")
    async def create_recipe(self, info: strawberry.Info, input: CreateRecipeInput) -> Recipe:
        user = require_user(info)
        return await service.resolve_create_recipe(user.id, input)

    @strawberry.mutation(
        description="Update an existing recipe. Only the recipe's author may do this."
    )
    async def update_recipe(
        self, info: strawberry.Info, id: strawberry.ID, input: UpdateRecipeInput
    ) -> Recipe:
        user = require_user(info)
        return await service.resolve_update_recipe(user.id, id, input)

    @strawberry.mutation(
        description="Delete a recipe. Only the recipe's author may do this. "
        "Idempotent for an already-deleted or unknown id."
    )
    async def delete_recipe(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        user = require_user(info)
        return await service.resolve_delete_recipe(user.id, id)

    @strawberry.mutation(
        description="Rate a recipe — upsert: rating the same recipe again updates "
        "your existing rating instead of creating a new one. Provide commentText to "
        "also leave or replace a comment on this rating."
    )
    async def rate_recipe(self, info: strawberry.Info, input: RateRecipeInput) -> Rating:
        user = require_user(info)
        return await ratings.resolve_rate_recipe(user.id, input)
