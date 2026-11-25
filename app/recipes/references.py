"""Helpers for the references a recipe holds: its category, ingredient lines and tags.

Used by create/update in service.py. Every client-supplied ID is parsed first and checked for
existence before anything is written, so a malformed or unknown ID is reported as a clear client
error instead of surfacing later as a foreign key violation ("Internal server error").
"""

import uuid
from decimal import Decimal

import strawberry
from sqlalchemy import delete, select

from errors import PublicError
from ids import parse_uuid
from models import MeasurementUnit as MeasurementUnitModel
from models import RecipeIngredient as RecipeIngredientModel
from models import recipe_tags
from recipes.inputs import RecipeIngredientInput


async def ensure_all_exist(session, model, ids: list[uuid.UUID], error: type[PublicError]) -> None:
    """Raise `error` unless every id refers to an existing row of `model`.

    A well-formed ID that doesn't exist would otherwise only be noticed by the database as a
    foreign key violation, which reaches the client as "Internal server error".
    """
    wanted = set(ids)
    if not wanted:
        return
    found = set((await session.execute(select(model.id).where(model.id.in_(wanted)))).scalars())
    if wanted - found:
        raise error()


def parse_ingredient_lines(
    lines: list[RecipeIngredientInput],
) -> list[tuple[uuid.UUID, RecipeIngredientInput]]:
    """Validate every ingredient ID up front, before anything is written to the database."""
    return [
        (parse_uuid(line.ingredient_id, f"ingredients[{index}].ingredientId"), line)
        for index, line in enumerate(lines)
    ]


def parse_tag_ids(tag_ids: list[strawberry.ID]) -> list[uuid.UUID]:
    parsed = [parse_uuid(tag_id, f"tagIds[{index}]") for index, tag_id in enumerate(tag_ids)]
    # A tag can be attached to a recipe only once; listing it twice is harmless, not an error.
    return list(dict.fromkeys(parsed))


async def replace_ingredients(
    session, recipe_id: uuid.UUID, lines: list[tuple[uuid.UUID, RecipeIngredientInput]]
) -> None:
    await session.execute(delete(RecipeIngredientModel).where(RecipeIngredientModel.recipe_id == recipe_id))
    for position, (ingredient_id, line) in enumerate(lines):
        session.add(
            RecipeIngredientModel(
                recipe_id=recipe_id,
                ingredient_id=ingredient_id,
                amount=Decimal(str(line.amount)),
                unit=MeasurementUnitModel(line.unit.value),
                position=position,
            )
        )


async def replace_tags(session, recipe_id: uuid.UUID, tag_ids: list[uuid.UUID]) -> None:
    await session.execute(recipe_tags.delete().where(recipe_tags.c.recipe_id == recipe_id))
    for tag_id in tag_ids:
        await session.execute(recipe_tags.insert().values(recipe_id=recipe_id, tag_id=tag_id))
