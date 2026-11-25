"""GraphQL output types for recipes, ingredients and ratings.

Nested fields (Recipe.author/category/ingredients/tags/ratings, Ingredient.category,
RecipeIngredient.ingredient, Rating.user) go through the per-request DataLoaders from
loaders.py (`info.context["loaders"]`), so a list of N recipes costs one batched query per
relation, not N.
"""

import uuid
from datetime import datetime

import strawberry

from recipes.enums import Difficulty, MeasurementUnit
from models import IngredientCatalog as IngredientCatalogModel
from models import IngredientCategory as IngredientCategoryModel
from models import Rating as RatingModel
from models import Recipe as RecipeModel
from models import RecipeCategory as RecipeCategoryModel
from models import RecipeIngredient as RecipeIngredientModel
from models import Tag as TagModel
from models import User as UserModel


@strawberry.type(description="The single category a recipe belongs to (e.g. Salads, Soups).")
class RecipeCategory:
    id: strawberry.ID
    name: str

    @staticmethod
    def from_model(model: RecipeCategoryModel) -> "RecipeCategory":
        return RecipeCategory(id=strawberry.ID(str(model.id)), name=model.name)


@strawberry.type(description="Grouping for ingredients (e.g. Meat, Vegetables).")
class IngredientCategory:
    id: strawberry.ID
    name: str

    @staticmethod
    def from_model(model: IngredientCategoryModel) -> "IngredientCategory":
        return IngredientCategory(id=strawberry.ID(str(model.id)), name=model.name)


@strawberry.type(description="A free-form label attached to a recipe (e.g. vegetarian).")
class Tag:
    id: strawberry.ID
    name: str

    @staticmethod
    def from_model(model: TagModel) -> "Tag":
        return Tag(id=strawberry.ID(str(model.id)), name=model.name)


@strawberry.type(description="An entry from the master ingredient list.")
class Ingredient:
    id: strawberry.ID
    name: str
    _category_id: strawberry.Private[uuid.UUID]

    @strawberry.field(description="The category this ingredient belongs to.")
    async def category(self, info: strawberry.Info) -> IngredientCategory:
        model = await info.context["loaders"].ingredient_category.load(self._category_id)
        return IngredientCategory.from_model(model)

    @staticmethod
    def from_model(model: IngredientCatalogModel) -> "Ingredient":
        return Ingredient(
            id=strawberry.ID(str(model.id)), name=model.name, _category_id=model.category_id
        )


@strawberry.type(description="One ingredient line in a recipe: which ingredient, how much, in what unit.")
class RecipeIngredient:
    amount: float
    unit: MeasurementUnit
    _ingredient_id: strawberry.Private[uuid.UUID]

    @strawberry.field(description="The ingredient from the master list.")
    async def ingredient(self, info: strawberry.Info) -> Ingredient:
        model = await info.context["loaders"].ingredient.load(self._ingredient_id)
        return Ingredient.from_model(model)

    @staticmethod
    def from_model(model: RecipeIngredientModel) -> "RecipeIngredient":
        return RecipeIngredient(
            amount=float(model.amount),
            unit=MeasurementUnit(model.unit.value),
            _ingredient_id=model.ingredient_id,
        )


@strawberry.type(description="The comment attached to a rating (SPEC.md §5: at most one per rating).")
class RatingComment:
    id: strawberry.ID
    text: str
    created_at: datetime
    updated_at: datetime


@strawberry.type(description="One user's rating of one recipe.")
class Rating:
    id: strawberry.ID
    value: int
    created_at: datetime
    updated_at: datetime
    comment: RatingComment | None
    _user_id: strawberry.Private[uuid.UUID]

    @strawberry.field(description="The user who left this rating.")
    async def user(self, info: strawberry.Info) -> "RecipeAuthor":
        model = await info.context["loaders"].user.load(self._user_id)
        return RecipeAuthor.from_model(model)


@strawberry.type(description="The author of a recipe — a minimal public view of a user.")
class RecipeAuthor:
    id: strawberry.ID
    username: str

    @staticmethod
    def from_model(model: UserModel) -> "RecipeAuthor":
        return RecipeAuthor(id=strawberry.ID(str(model.id)), username=model.username)


@strawberry.type(description="A single recipe in the catalog.")
class Recipe:
    id: strawberry.ID
    title: str
    description: str | None
    cooking_time_minutes: int
    difficulty: Difficulty
    servings: int
    _author_id: strawberry.Private[uuid.UUID]
    _category_id: strawberry.Private[uuid.UUID]

    @strawberry.field(description="Who created this recipe.")
    async def author(self, info: strawberry.Info) -> RecipeAuthor:
        model = await info.context["loaders"].user.load(self._author_id)
        return RecipeAuthor.from_model(model)

    @strawberry.field(description="The single category this recipe belongs to.")
    async def category(self, info: strawberry.Info) -> RecipeCategory:
        model = await info.context["loaders"].recipe_category.load(self._category_id)
        return RecipeCategory.from_model(model)

    @strawberry.field(description="Ingredients, in the order they were listed.")
    async def ingredients(self, info: strawberry.Info) -> list[RecipeIngredient]:
        rows = await info.context["loaders"].ingredients_by_recipe.load(uuid.UUID(self.id))
        return [RecipeIngredient.from_model(row) for row in rows]

    @strawberry.field(description="Free-form tags attached to this recipe.")
    async def tags(self, info: strawberry.Info) -> list[Tag]:
        rows = await info.context["loaders"].tags_by_recipe.load(uuid.UUID(self.id))
        return [Tag.from_model(tag) for tag in rows]

    @strawberry.field(description="All ratings left on this recipe.")
    async def ratings(self, info: strawberry.Info) -> list[Rating]:
        rows = await info.context["loaders"].ratings_by_recipe.load(uuid.UUID(self.id))
        return [rating_from_model(row) for row in rows]

    @strawberry.field(description="Average rating, or null if the recipe has no ratings yet.")
    async def avg_rating(self, info: strawberry.Info) -> float | None:
        # Reuses the same batched ratings load as `ratings` / `ratingsCount` — no extra query.
        rows = await info.context["loaders"].ratings_by_recipe.load(uuid.UUID(self.id))
        return sum(row.value for row in rows) / len(rows) if rows else None

    @strawberry.field(description="How many ratings this recipe has.")
    async def ratings_count(self, info: strawberry.Info) -> int:
        rows = await info.context["loaders"].ratings_by_recipe.load(uuid.UUID(self.id))
        return len(rows)

    @staticmethod
    def from_model(model: RecipeModel) -> "Recipe":
        return Recipe(
            id=strawberry.ID(str(model.id)),
            title=model.title,
            description=model.description,
            cooking_time_minutes=model.cooking_time_minutes,
            difficulty=Difficulty(model.difficulty.value),
            servings=model.servings,
            _author_id=model.author_id,
            _category_id=model.category_id,
        )


def rating_from_model(model: RatingModel) -> Rating:
    comment = None
    if model.comment is not None:
        comment = RatingComment(
            id=strawberry.ID(str(model.comment.id)),
            text=model.comment.text,
            created_at=model.comment.created_at,
            updated_at=model.comment.updated_at,
        )
    return Rating(
        id=strawberry.ID(str(model.id)),
        value=model.value,
        created_at=model.created_at,
        updated_at=model.updated_at,
        comment=comment,
        _user_id=model.user_id,
    )
