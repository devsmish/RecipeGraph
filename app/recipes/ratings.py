"""The rateRecipe logic: upsert a user's rating (and optional comment) of a recipe."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from db import async_session_maker
from errors import PublicError
from ids import parse_uuid
from recipes.errors import (
    MAX_RATING_VALUE,
    MIN_RATING_VALUE,
    InvalidRatingValueError,
    RecipeNotFoundError,
)
from recipes.inputs import RateRecipeInput
from recipes.types import Rating, rating_from_model
from models import Rating as RatingModel
from models import RatingComment as RatingCommentModel
from models import Recipe as RecipeModel

# PostgreSQL error codes and constraint names (see the `ratings` table in models.py).
_PG_FOREIGN_KEY_VIOLATION = "23503"
_PG_CHECK_VIOLATION = "23514"
_RATING_VALUE_CHECK = "ck_rating_value_range"


def _map_rating_integrity_error(exc: IntegrityError) -> PublicError | None:
    """Translate a database integrity error from saving a rating into a client-facing error.

    Only failures we can explain to the client are mapped: the rating-range CHECK constraint
    and a foreign key on the recipe (the recipe was deleted after we looked it up). Anything
    else — a unique violation from a concurrent first rating, a missing user, ... — returns
    None, so the caller lets it propagate as the unexpected error it is (masked for the
    client, logged and reported to Sentry) rather than mislabelling it as a bad rating value.
    """
    sqlstate = getattr(exc.orig, "sqlstate", None)
    constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None) or ""

    if sqlstate == _PG_CHECK_VIOLATION and constraint == _RATING_VALUE_CHECK:
        return InvalidRatingValueError()
    if sqlstate == _PG_FOREIGN_KEY_VIOLATION and "recipe_id" in constraint:
        return RecipeNotFoundError()
    return None


async def resolve_rate_recipe(user_id: uuid.UUID, input: RateRecipeInput) -> Rating:
    recipe_id = parse_uuid(input.recipe_id, "recipeId")
    # Validate the value before any database work; the CHECK constraint stays as a safety net.
    if not MIN_RATING_VALUE <= input.value <= MAX_RATING_VALUE:
        raise InvalidRatingValueError()

    async with async_session_maker() as session:
        recipe_exists = await session.execute(select(RecipeModel.id).where(RecipeModel.id == recipe_id))
        if recipe_exists.scalar_one_or_none() is None:
            raise RecipeNotFoundError()

        # Upsert by the UNIQUE(recipe_id, user_id) constraint: changing
        # a rating updates this same row rather than creating a new one.
        existing = await session.execute(
            select(RatingModel).where(
                RatingModel.recipe_id == recipe_id,
                RatingModel.user_id == user_id,
            )
        )
        rating = existing.scalar_one_or_none()

        if rating is None:
            rating = RatingModel(recipe_id=recipe_id, user_id=user_id, value=input.value)
            session.add(rating)
        else:
            rating.value = input.value

        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            mapped = _map_rating_integrity_error(exc)
            if mapped is None:
                raise  # unexpected: let the error handler mask, log and report it
            raise mapped from exc

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
        return rating_from_model(final.scalar_one())
