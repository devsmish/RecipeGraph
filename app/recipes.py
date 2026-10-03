"""GraphQL types and resolvers for recipes, ingredients, and their dictionaries.

Nested fields on Recipe (author, category, ingredients, tags, ratings) are
deliberately naive resolvers — one query each, no batching.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

import strawberry
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from db import async_session_maker
from models import Difficulty as DifficultyModel
from models import IngredientCatalog as IngredientCatalogModel
from models import IngredientCategory as IngredientCategoryModel
from models import MeasurementUnit as MeasurementUnitModel
from models import Rating as RatingModel
from models import RatingComment as RatingCommentModel
from models import Recipe as RecipeModel
from models import RecipeCategory as RecipeCategoryModel
from models import RecipeIngredient as RecipeIngredientModel
from models import Tag as TagModel
from models import User as UserModel
from models import recipe_tags


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


# Mutations


class NotRecipeOwnerError(Exception):
    def __init__(self) -> None:
        super().__init__("You can only modify your own recipes")


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


async def _replace_ingredients(session, recipe_id: uuid.UUID, lines: list[RecipeIngredientInput]) -> None:
    await session.execute(delete(RecipeIngredientModel).where(RecipeIngredientModel.recipe_id == recipe_id))
    for position, line in enumerate(lines):
        session.add(
            RecipeIngredientModel(
                recipe_id=recipe_id,
                ingredient_id=uuid.UUID(line.ingredient_id),
                amount=Decimal(str(line.amount)),
                unit=MeasurementUnitModel(line.unit.value),
                position=position,
            )
        )


async def _replace_tags(session, recipe_id: uuid.UUID, tag_ids: list[strawberry.ID]) -> None:
    await session.execute(recipe_tags.delete().where(recipe_tags.c.recipe_id == recipe_id))
    for tag_id in tag_ids:
        await session.execute(recipe_tags.insert().values(recipe_id=recipe_id, tag_id=uuid.UUID(tag_id)))


async def resolve_create_recipe(user_id: uuid.UUID, input: CreateRecipeInput) -> Recipe:
    async with async_session_maker() as session:
        recipe = RecipeModel(
            author_id=user_id,
            category_id=uuid.UUID(input.category_id),
            title=input.title,
            description=input.description,
            cooking_time_minutes=input.cooking_time_minutes,
            difficulty=DifficultyModel(input.difficulty.value),
            servings=input.servings,
        )
        session.add(recipe)
        await session.flush()  # assigns recipe.id, needed by the two helpers below

        await _replace_ingredients(session, recipe.id, input.ingredients)
        await _replace_tags(session, recipe.id, list(input.tag_ids))

        await session.commit()
        return Recipe.from_model(recipe)


async def resolve_update_recipe(user_id: uuid.UUID, recipe_id: strawberry.ID, input: UpdateRecipeInput) -> Recipe:
    async with async_session_maker() as session:
        result = await session.execute(select(RecipeModel).where(RecipeModel.id == uuid.UUID(recipe_id)))
        recipe = result.scalar_one_or_none()
        if recipe is None:
            raise RecipeNotFoundError()
        if recipe.author_id != user_id:
            raise NotRecipeOwnerError()

        # strawberry.UNSET distinguishes "field not provided in the mutation" from
        # "field explicitly set to null" — the latter matters for `description`,
        # which is nullable in the schema (SPEC.md §5) and should be clearable.
        if input.category_id is not strawberry.UNSET:
            recipe.category_id = uuid.UUID(input.category_id)
        if input.title is not strawberry.UNSET:
            recipe.title = input.title
        if input.description is not strawberry.UNSET:
            recipe.description = input.description
        if input.cooking_time_minutes is not strawberry.UNSET:
            recipe.cooking_time_minutes = input.cooking_time_minutes
        if input.difficulty is not strawberry.UNSET:
            recipe.difficulty = DifficultyModel(input.difficulty.value)
        if input.servings is not strawberry.UNSET:
            recipe.servings = input.servings
        if input.ingredients is not strawberry.UNSET:
            await _replace_ingredients(session, recipe.id, input.ingredients)
        if input.tag_ids is not strawberry.UNSET:
            await _replace_tags(session, recipe.id, list(input.tag_ids))

        await session.commit()
        return Recipe.from_model(recipe)


async def resolve_delete_recipe(user_id: uuid.UUID, recipe_id: strawberry.ID) -> bool:
    async with async_session_maker() as session:
        result = await session.execute(select(RecipeModel).where(RecipeModel.id == uuid.UUID(recipe_id)))
        recipe = result.scalar_one_or_none()

        if recipe is None:
            return False
        if recipe.author_id != user_id:
            raise NotRecipeOwnerError()

        await session.delete(recipe)
        await session.commit()
        return True


# rateRecipe


class InvalidRatingValueError(Exception):
    def __init__(self) -> None:
        super().__init__("Rating value must be between 1 and 5")


@strawberry.input(
    description="Fields for rating a recipe. Provide commentText to also leave or "
    "replace a comment on this rating — omit it to leave any existing comment untouched."
)
class RateRecipeInput:
    recipe_id: strawberry.ID
    value: int
    comment_text: str | None = None


async def resolve_rate_recipe(user_id: uuid.UUID, input: RateRecipeInput) -> Rating:
    async with async_session_maker() as session:
        recipe_exists = await session.execute(
            select(RecipeModel.id).where(RecipeModel.id == uuid.UUID(input.recipe_id))
        )
        if recipe_exists.scalar_one_or_none() is None:
            raise RecipeNotFoundError()

        # Upsert by the UNIQUE(recipe_id, user_id) constraint: changing
        # a rating updates this same row rather than creating a new one.
        existing = await session.execute(
            select(RatingModel).where(
                RatingModel.recipe_id == uuid.UUID(input.recipe_id),
                RatingModel.user_id == user_id,
            )
        )
        rating = existing.scalar_one_or_none()

        if rating is None:
            rating = RatingModel(recipe_id=uuid.UUID(input.recipe_id), user_id=user_id, value=input.value)
            session.add(rating)
        else:
            rating.value = input.value

        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise InvalidRatingValueError() from exc

        if input.comment_text is not None:
            # UNIQUE(rating_id): at most one comment per rating.
            comment_result = await session.execute(
                select(RatingCommentModel).where(RatingCommentModel.rating_id == rating.id)
            )
            comment = comment_result.scalar_one_or_none()
            if comment is None:
                session.add(RatingCommentModel(rating_id=rating.id, text=input.comment_text))
            else:
                comment.text = input.comment_text

        await session.commit()

        # Reload with the comment relationship populated for the response.
        final = await session.execute(
            select(RatingModel).where(RatingModel.id == rating.id).options(selectinload(RatingModel.comment))
        )
        return _rating_from_model(final.scalar_one())
