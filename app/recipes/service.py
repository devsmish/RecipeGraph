"""Database logic behind the recipe queries and the create/update/delete mutations.

The GraphQL fields in queries.py and mutations.py are thin: they check authentication and call a
function here. Client-supplied IDs are parsed (ids.parse_uuid) and checked for existence before
anything is written, so a bad request changes nothing.
"""

import uuid

import strawberry
from sqlalchemy import select

from db import async_session_maker
from ids import parse_uuid
from recipes.errors import (
    CategoryNotFoundError,
    IngredientNotFoundError,
    NotRecipeOwnerError,
    RecipeNotFoundError,
    TagNotFoundError,
)
from recipes.inputs import CreateRecipeInput, UpdateRecipeInput
from recipes.references import (
    ensure_all_exist,
    parse_ingredient_lines,
    parse_tag_ids,
    replace_ingredients,
    replace_tags,
)
from recipes.types import Ingredient, IngredientCategory, Recipe, RecipeCategory
from models import Difficulty as DifficultyModel
from models import IngredientCatalog as IngredientCatalogModel
from models import IngredientCategory as IngredientCategoryModel
from models import Recipe as RecipeModel
from models import RecipeCategory as RecipeCategoryModel
from models import Tag as TagModel


async def resolve_recipe(recipe_id: strawberry.ID) -> Recipe:
    parsed_id = parse_uuid(recipe_id, "id")
    async with async_session_maker() as session:
        result = await session.execute(select(RecipeModel).where(RecipeModel.id == parsed_id))
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


async def resolve_create_recipe(user_id: uuid.UUID, input: CreateRecipeInput) -> Recipe:
    # Validate every client-supplied ID first, so a malformed one is rejected before
    # anything is written to the database.
    category_id = parse_uuid(input.category_id, "categoryId")
    ingredient_lines = parse_ingredient_lines(input.ingredients)
    tag_ids = parse_tag_ids(list(input.tag_ids))

    async with async_session_maker() as session:
        await ensure_all_exist(session, RecipeCategoryModel, [category_id], CategoryNotFoundError)
        await ensure_all_exist(
            session,
            IngredientCatalogModel,
            [ingredient_id for ingredient_id, _ in ingredient_lines],
            IngredientNotFoundError,
        )
        await ensure_all_exist(session, TagModel, tag_ids, TagNotFoundError)

        recipe = RecipeModel(
            author_id=user_id,
            category_id=category_id,
            title=input.title,
            description=input.description,
            cooking_time_minutes=input.cooking_time_minutes,
            difficulty=DifficultyModel(input.difficulty.value),
            servings=input.servings,
        )
        session.add(recipe)
        await session.flush()  # assigns recipe.id, needed by the two helpers below

        await replace_ingredients(session, recipe.id, ingredient_lines)
        await replace_tags(session, recipe.id, tag_ids)

        await session.commit()
        return Recipe.from_model(recipe)


async def resolve_update_recipe(user_id: uuid.UUID, recipe_id: strawberry.ID, input: UpdateRecipeInput) -> Recipe:
    # Validate every client-supplied ID first (see resolve_create_recipe).
    parsed_recipe_id = parse_uuid(recipe_id, "id")
    category_id = (
        parse_uuid(input.category_id, "categoryId") if input.category_id is not strawberry.UNSET else None
    )
    ingredient_lines = (
        parse_ingredient_lines(input.ingredients) if input.ingredients is not strawberry.UNSET else None
    )
    tag_ids = parse_tag_ids(list(input.tag_ids)) if input.tag_ids is not strawberry.UNSET else None

    async with async_session_maker() as session:
        result = await session.execute(select(RecipeModel).where(RecipeModel.id == parsed_recipe_id))
        recipe = result.scalar_one_or_none()
        if recipe is None:
            raise RecipeNotFoundError()
        if recipe.author_id != user_id:
            raise NotRecipeOwnerError()

        if category_id is not None:
            await ensure_all_exist(session, RecipeCategoryModel, [category_id], CategoryNotFoundError)
        if ingredient_lines is not None:
            await ensure_all_exist(
                session,
                IngredientCatalogModel,
                [ingredient_id for ingredient_id, _ in ingredient_lines],
                IngredientNotFoundError,
            )
        if tag_ids is not None:
            await ensure_all_exist(session, TagModel, tag_ids, TagNotFoundError)

        # strawberry.UNSET distinguishes "field not provided in the mutation" from
        # "field explicitly set to null" — the latter matters for `description`,
        # which is nullable in the schema (SPEC.md §5) and should be clearable.
        if category_id is not None:
            recipe.category_id = category_id
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
        if ingredient_lines is not None:
            await replace_ingredients(session, recipe.id, ingredient_lines)
        if tag_ids is not None:
            await replace_tags(session, recipe.id, tag_ids)

        await session.commit()
        return Recipe.from_model(recipe)


async def resolve_delete_recipe(user_id: uuid.UUID, recipe_id: strawberry.ID) -> bool:
    parsed_recipe_id = parse_uuid(recipe_id, "id")
    async with async_session_maker() as session:
        result = await session.execute(select(RecipeModel).where(RecipeModel.id == parsed_recipe_id))
        recipe = result.scalar_one_or_none()

        if recipe is None:
            return False
        if recipe.author_id != user_id:
            raise NotRecipeOwnerError()

        await session.delete(recipe)
        await session.commit()
        return True
