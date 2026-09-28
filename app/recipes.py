"""GraphQL types and resolvers for recipes, ingredients, and their dictionaries.

Nested fields on Recipe (author, category, ingredients, tags, ratings) are
deliberately naive resolvers — one query each, no batching.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

import strawberry
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db import async_session_maker
from models import Difficulty as DifficultyModel
from models import IngredientCatalog as IngredientCatalogModel
from models import IngredientCategory as IngredientCategoryModel
from models import MeasurementUnit as MeasurementUnitModel
from models import Rating as RatingModel
from models import Recipe as RecipeModel
from models import RecipeCategory as RecipeCategoryModel
from models import RecipeIngredient as RecipeIngredientModel
from models import Tag as TagModel
from models import User as UserModel


@strawberry.enum(description="How difficult a recipe is to make.")
class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@strawberry.enum(description="Unit of measurement for a recipe ingredient's amount.")
class MeasurementUnit(Enum):
    G = "g"
    KG = "kg"
    ML = "ml"
    L = "l"
    PCS = "pcs"
    TBSP = "tbsp"
    TSP = "tsp"
    PINCH = "pinch"
    TO_TASTE = "to_taste"


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
    async def category(self) -> IngredientCategory:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IngredientCategoryModel).where(IngredientCategoryModel.id == self._category_id)
            )
            return IngredientCategory.from_model(result.scalar_one())

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
    async def ingredient(self) -> Ingredient:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IngredientCatalogModel).where(IngredientCatalogModel.id == self._ingredient_id)
            )
            return Ingredient.from_model(result.scalar_one())

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
    async def user(self) -> "RecipeAuthor":
        async with async_session_maker() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == self._user_id))
            return RecipeAuthor.from_model(result.scalar_one())


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
    async def author(self) -> RecipeAuthor:
        async with async_session_maker() as session:
            result = await session.execute(select(UserModel).where(UserModel.id == self._author_id))
            return RecipeAuthor.from_model(result.scalar_one())

    @strawberry.field(description="The single category this recipe belongs to.")
    async def category(self) -> RecipeCategory:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RecipeCategoryModel).where(RecipeCategoryModel.id == self._category_id)
            )
            return RecipeCategory.from_model(result.scalar_one())

    @strawberry.field(description="Ingredients, in the order they were listed.")
    async def ingredients(self) -> list[RecipeIngredient]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RecipeIngredientModel)
                .where(RecipeIngredientModel.recipe_id == uuid.UUID(self.id))
                .order_by(RecipeIngredientModel.position)
            )
            return [RecipeIngredient.from_model(row) for row in result.scalars()]

    @strawberry.field(description="Free-form tags attached to this recipe.")
    async def tags(self) -> list[Tag]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RecipeModel)
                .where(RecipeModel.id == uuid.UUID(self.id))
                .options(selectinload(RecipeModel.tags))
            )
            recipe = result.scalar_one()
            return [Tag.from_model(tag) for tag in recipe.tags]

    @strawberry.field(description="All ratings left on this recipe.")
    async def ratings(self) -> list[Rating]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RatingModel)
                .where(RatingModel.recipe_id == uuid.UUID(self.id))
                .options(selectinload(RatingModel.comment))
            )
            return [_rating_from_model(row) for row in result.scalars()]

    @strawberry.field(description="Average rating, or null if the recipe has no ratings yet.")
    async def avg_rating(self) -> float | None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RatingModel.value).where(RatingModel.recipe_id == uuid.UUID(self.id))
            )
            values = list(result.scalars())
            return sum(values) / len(values) if values else None

    @strawberry.field(description="How many ratings this recipe has.")
    async def ratings_count(self) -> int:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RatingModel.id).where(RatingModel.recipe_id == uuid.UUID(self.id))
            )
            return len(list(result.scalars()))

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


def _rating_from_model(model: RatingModel) -> Rating:
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


class RecipeNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__("Recipe not found")


async def resolve_recipe(recipe_id: strawberry.ID) -> Recipe:
    async with async_session_maker() as session:
        result = await session.execute(
            select(RecipeModel).where(RecipeModel.id == uuid.UUID(recipe_id))
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise RecipeNotFoundError()
        return Recipe.from_model(model)


async def resolve_my_recipes(user_id: uuid.UUID) -> list[Recipe]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(RecipeModel).where(RecipeModel.author_id == user_id)
        )
        return [Recipe.from_model(row) for row in result.scalars()]


async def resolve_recipe_categories() -> list[RecipeCategory]:
    async with async_session_maker() as session:
        result = await session.execute(select(RecipeCategoryModel).order_by(RecipeCategoryModel.name))
        return [RecipeCategory.from_model(row) for row in result.scalars()]


async def resolve_ingredient_categories() -> list[IngredientCategory]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(IngredientCategoryModel).order_by(IngredientCategoryModel.name)
        )
        return [IngredientCategory.from_model(row) for row in result.scalars()]


async def resolve_ingredients(search: str | None) -> list[Ingredient]:
    async with async_session_maker() as session:
        query = select(IngredientCatalogModel).order_by(IngredientCatalogModel.name)
        if search:
            query = query.where(IngredientCatalogModel.name.ilike(f"%{search}%"))
        result = await session.execute(query)
        return [Ingredient.from_model(row) for row in result.scalars()]
