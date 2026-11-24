"""Client-facing errors of the recipe API (all are `PublicError`, so their messages reach the client)."""

from errors import PublicError

# The rating scale. It is also enforced by the `ck_rating_value_range` CHECK constraint on the
# `ratings` table (models.py), so change both together.
MIN_RATING_VALUE = 1
MAX_RATING_VALUE = 5
_RATING_RANGE_MESSAGE = f"Rating value must be between {MIN_RATING_VALUE} and {MAX_RATING_VALUE}"


class RecipeNotFoundError(PublicError):
    def __init__(self) -> None:
        super().__init__("Recipe not found")


class NotRecipeOwnerError(PublicError):
    def __init__(self) -> None:
        super().__init__("You can only modify your own recipes")


class CategoryNotFoundError(PublicError):
    def __init__(self) -> None:
        super().__init__("Recipe category not found")


class IngredientNotFoundError(PublicError):
    def __init__(self) -> None:
        super().__init__("Ingredient not found")


class TagNotFoundError(PublicError):
    def __init__(self) -> None:
        super().__init__("Tag not found")


class InvalidRatingValueError(PublicError):
    def __init__(self) -> None:
        super().__init__(_RATING_RANGE_MESSAGE)
