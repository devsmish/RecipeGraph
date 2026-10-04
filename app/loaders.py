"""Per-request DataLoaders — batch and deduplicate the DB lookups behind nested fields.

The problem (N+1): for `myRecipes { author { username } }` with 20 recipes, a naive
`author` resolver runs one SELECT per recipe — 1 query for the list + 20 for authors.

A DataLoader fixes this by collecting every `.load(key)` call made during the same tick
of the event loop and calling one batch function with all the keys at once:
`SELECT ... WHERE id IN (k1, k2, ...)`. It also caches by key, so asking for the same
key twice in one request (e.g. the same author on 10 recipes) costs nothing extra.

Two rules every batch function here follows (the DataLoader contract):
- return exactly one result per key, in the same order as the keys — the database
  returns rows in whatever order it likes, so we re-map them by key explicitly;
- a key with no matching rows still gets an entry: `[]` for one-to-many loaders, a
  `LookupError` for many-to-one loaders (surfaced as a GraphQL error for that field only).

Loaders are created fresh for every request (see `context.get_context`), never shared
globally: the cache must not outlive the request, or one user's data (or stale data
after a mutation) could be served to the next request.
"""

import uuid
from collections import defaultdict
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from strawberry.dataloader import DataLoader

from db import async_session_maker
from models import IngredientCatalog as IngredientCatalogModel
from models import IngredientCategory as IngredientCategoryModel
from models import Rating as RatingModel
from models import RecipeCategory as RecipeCategoryModel
from models import RecipeIngredient as RecipeIngredientModel
from models import Tag as TagModel
from models import User as UserModel
from models import recipe_tags


def _many_to_one(model):
    """Build a batch function that loads `model` rows by primary key (one result per key)."""

    async def load_fn(keys: list[uuid.UUID]) -> list:
        async with async_session_maker() as session:
            result = await session.execute(select(model).where(model.id.in_(keys)))
            by_id = {row.id: row for row in result.scalars()}
        return [by_id.get(key) or LookupError(f"{model.__name__} {key} not found") for key in keys]

    return load_fn


def _group(rows: Sequence[tuple[Hashable, object]], keys: list[uuid.UUID]) -> list[list]:
    """Group (key, item) pairs by key, returning one list per requested key, in key order.
    A key with no rows gets `[]` — never a missing entry."""
    grouped: dict[Hashable, list] = defaultdict(list)
    for key, item in rows:
        grouped[key].append(item)
    return [grouped.get(key, []) for key in keys]


async def _ingredients_by_recipe(recipe_ids: list[uuid.UUID]) -> list[list[RecipeIngredientModel]]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(RecipeIngredientModel)
            .where(RecipeIngredientModel.recipe_id.in_(recipe_ids))
            .order_by(RecipeIngredientModel.position)
        )
        rows = [(row.recipe_id, row) for row in result.scalars()]
    return _group(rows, recipe_ids)


async def _tags_by_recipe(recipe_ids: list[uuid.UUID]) -> list[list[TagModel]]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(recipe_tags.c.recipe_id, TagModel)
            .join(TagModel, TagModel.id == recipe_tags.c.tag_id)
            .where(recipe_tags.c.recipe_id.in_(recipe_ids))
            .order_by(TagModel.name)
        )
        rows = [(recipe_id, tag) for recipe_id, tag in result.all()]
    return _group(rows, recipe_ids)


async def _ratings_by_recipe(recipe_ids: list[uuid.UUID]) -> list[list[RatingModel]]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(RatingModel)
            .where(RatingModel.recipe_id.in_(recipe_ids))
            # The 1:1 comment comes along in the same query (JOIN), not a second one.
            .options(joinedload(RatingModel.comment))
            .order_by(RatingModel.created_at, RatingModel.id)
        )
        rows = [(row.recipe_id, row) for row in result.scalars()]
    return _group(rows, recipe_ids)


@dataclass
class Loaders:
    """All DataLoaders for one GraphQL request."""

    # many-to-one: key = id of the related row, value = that row
    user: DataLoader  # recipe author, rating author
    recipe_category: DataLoader
    ingredient: DataLoader  # master-list entry behind a recipe's ingredient line
    ingredient_category: DataLoader
    # one-to-many: key = recipe id, value = list of child rows (possibly empty)
    ingredients_by_recipe: DataLoader
    tags_by_recipe: DataLoader
    ratings_by_recipe: DataLoader


def create_loaders() -> Loaders:
    return Loaders(
        user=DataLoader(load_fn=_many_to_one(UserModel)),
        recipe_category=DataLoader(load_fn=_many_to_one(RecipeCategoryModel)),
        ingredient=DataLoader(load_fn=_many_to_one(IngredientCatalogModel)),
        ingredient_category=DataLoader(load_fn=_many_to_one(IngredientCategoryModel)),
        ingredients_by_recipe=DataLoader(load_fn=_ingredients_by_recipe),
        tags_by_recipe=DataLoader(load_fn=_tags_by_recipe),
        ratings_by_recipe=DataLoader(load_fn=_ratings_by_recipe),
    )
