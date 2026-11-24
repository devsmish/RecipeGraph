"""Recipes: GraphQL types, inputs, errors, service logic, queries and mutations.

The public names are re-exported here, so the rest of the application imports from `recipes`
without caring which module defines them:

    types.py       output types (Recipe, Rating, ...)        enums.py       Difficulty, MeasurementUnit
    inputs.py      input types for mutations                 errors.py      client-facing errors, rating scale
    service.py     queries and create/update/delete logic    ratings.py     rateRecipe logic
    references.py  validation of IDs a recipe refers to      queries.py / mutations.py   the GraphQL fields
"""

from recipes.enums import Difficulty, MeasurementUnit
from recipes.errors import (
    CategoryNotFoundError,
    IngredientNotFoundError,
    InvalidRatingValueError,
    NotRecipeOwnerError,
    RecipeNotFoundError,
    TagNotFoundError,
)
from recipes.inputs import CreateRecipeInput, RateRecipeInput, RecipeIngredientInput, UpdateRecipeInput
from recipes.mutations import RecipeMutation
from recipes.queries import RecipeQuery
from recipes.types import (
    Ingredient,
    IngredientCategory,
    Rating,
    RatingComment,
    Recipe,
    RecipeAuthor,
    RecipeCategory,
    RecipeIngredient,
    Tag,
)

__all__ = [
    "CategoryNotFoundError",
    "CreateRecipeInput",
    "Difficulty",
    "Ingredient",
    "IngredientCategory",
    "IngredientNotFoundError",
    "InvalidRatingValueError",
    "MeasurementUnit",
    "NotRecipeOwnerError",
    "RateRecipeInput",
    "Rating",
    "RatingComment",
    "Recipe",
    "RecipeAuthor",
    "RecipeCategory",
    "RecipeIngredient",
    "RecipeIngredientInput",
    "RecipeMutation",
    "RecipeNotFoundError",
    "RecipeQuery",
    "Tag",
    "TagNotFoundError",
    "UpdateRecipeInput",
]
