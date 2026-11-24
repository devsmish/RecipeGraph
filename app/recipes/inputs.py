"""GraphQL input types for recipe mutations."""

import strawberry

from recipes.enums import Difficulty, MeasurementUnit


@strawberry.input(description="One ingredient line: which ingredient, how much, in what unit.")
class RecipeIngredientInput:
    ingredient_id: strawberry.ID
    amount: float
    unit: MeasurementUnit


@strawberry.input(description="Fields required to create a new recipe.")
class CreateRecipeInput:
    category_id: strawberry.ID
    title: str
    cooking_time_minutes: int
    difficulty: Difficulty
    servings: int
    ingredients: list[RecipeIngredientInput]
    description: str | None = None
    tag_ids: list[strawberry.ID] = strawberry.field(default_factory=list)


@strawberry.input(
    description="Fields to update on an existing recipe — omit a field to leave it "
    "unchanged. Providing `ingredients` or `tagIds` replaces the full list, not a merge."
)
class UpdateRecipeInput:
    category_id: strawberry.ID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET
    description: str | None = strawberry.UNSET
    cooking_time_minutes: int | None = strawberry.UNSET
    difficulty: Difficulty | None = strawberry.UNSET
    servings: int | None = strawberry.UNSET
    ingredients: list[RecipeIngredientInput] | None = strawberry.UNSET
    tag_ids: list[strawberry.ID] | None = strawberry.UNSET


@strawberry.input(
    description="Fields for rating a recipe. Provide commentText to also leave or "
    "replace a comment on this rating — omit it to leave any existing comment untouched."
)
class RateRecipeInput:
    recipe_id: strawberry.ID
    value: int
    comment_text: str | None = None
