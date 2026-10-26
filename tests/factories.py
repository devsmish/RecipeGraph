"""Async factories for test data.

Each factory writes its row(s) to the test database in its own transaction, commits, and
returns the model instance. Anything not given is filled with a sensible default, and the
objects it depends on are created on demand — so `await create_recipe()` is a complete,
valid recipe (author, category and all), and tests spell out only what they actually care
about:

    recipe = await create_recipe(title="Soup", ingredients=[tomato, onion], tags=[vegan])
    rating = await create_rating(recipe=recipe, value=5, comment="Great!")

Defaults that must be unique (usernames, emails, names) come from a counter, so calling a
factory repeatedly never collides. Instances stay usable after the session closes
(`expire_on_commit=False` in db.py), so tests can read their attributes freely.
"""

import itertools
from collections.abc import Sequence

from auth import create_access_token
from db import async_session_maker
from models import (
    Difficulty,
    IngredientCatalog,
    IngredientCategory,
    MeasurementUnit,
    Rating,
    RatingComment,
    Recipe,
    RecipeCategory,
    RecipeIngredient,
    Tag,
    User,
    recipe_tags,
)

_counter = itertools.count(1)


def _unique(prefix: str) -> str:
    return f"{prefix} {next(_counter)}"


async def _add(*rows):
    async with async_session_maker() as session:
        session.add_all(rows)
        await session.commit()
    return rows[0] if len(rows) == 1 else rows


async def create_user(
    *, username: str | None = None, email: str | None = None, password_hash: str = "x"
) -> User:
    n = next(_counter)
    return await _add(
        User(
            username=username or f"user{n}",
            email=email or f"user{n}@example.com",
            password_hash=password_hash,
        )
    )


def access_token_for(user: User) -> str:
    """A valid access token for `user`, as the API would issue it."""
    return create_access_token(user.id)


async def create_recipe_category(*, name: str | None = None) -> RecipeCategory:
    return await _add(RecipeCategory(name=name or _unique("Recipe category")))


async def create_ingredient_category(*, name: str | None = None) -> IngredientCategory:
    return await _add(IngredientCategory(name=name or _unique("Ingredient category")))


async def create_ingredient(
    *, name: str | None = None, category: IngredientCategory | None = None
) -> IngredientCatalog:
    category = category or await create_ingredient_category()
    return await _add(IngredientCatalog(name=name or _unique("Ingredient"), category_id=category.id))


async def create_tag(*, name: str | None = None) -> Tag:
    return await _add(Tag(name=name or _unique("tag")))


async def create_recipe(
    *,
    author: User | None = None,
    category: RecipeCategory | None = None,
    title: str | None = None,
    description: str | None = None,
    cooking_time_minutes: int = 10,
    difficulty: Difficulty = Difficulty.EASY,
    servings: int = 2,
    ingredients: Sequence[IngredientCatalog | tuple[IngredientCatalog, float, MeasurementUnit]] = (),
    tags: Sequence[Tag] = (),
) -> Recipe:
    """A recipe with its ingredient lines and tags.

    `ingredients` takes catalog entries (1 g each) or `(ingredient, amount, unit)` tuples; lines
    keep the order given, as `position`. Author and category are created when not passed.
    """
    author = author or await create_user()
    category = category or await create_recipe_category()

    async with async_session_maker() as session:
        recipe = Recipe(
            author_id=author.id,
            category_id=category.id,
            title=title or _unique("Recipe"),
            description=description,
            cooking_time_minutes=cooking_time_minutes,
            difficulty=difficulty,
            servings=servings,
        )
        session.add(recipe)
        await session.flush()

        for position, line in enumerate(ingredients):
            ingredient, amount, unit = line if isinstance(line, tuple) else (line, 1, MeasurementUnit.G)
            session.add(
                RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=ingredient.id,
                    amount=amount,
                    unit=unit,
                    position=position,
                )
            )
        for tag in tags:
            await session.execute(recipe_tags.insert().values(recipe_id=recipe.id, tag_id=tag.id))

        await session.commit()
    return recipe


async def create_rating(
    *,
    recipe: Recipe | None = None,
    user: User | None = None,
    value: int = 4,
    comment: str | None = None,
) -> Rating:
    """A rating (and, if `comment` is given, its comment) by `user` on `recipe`."""
    recipe = recipe or await create_recipe()
    user = user or await create_user()

    async with async_session_maker() as session:
        rating = Rating(recipe_id=recipe.id, user_id=user.id, value=value)
        session.add(rating)
        await session.flush()
        if comment is not None:
            session.add(RatingComment(rating_id=rating.id, text=comment))
        await session.commit()
    return rating
