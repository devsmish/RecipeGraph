"""SQLAlchemy ORM models for RecipeGraph."""

from __future__ import annotations

import datetime
import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base — every model below inherits from this."""


# Enums
# Stored as native PostgreSQL ENUM types (not plain strings) so the database
# itself rejects invalid values, not just the application layer.


class Difficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class MeasurementUnit(str, enum.Enum):
    G = "g"
    KG = "kg"
    ML = "ml"
    L = "l"
    PCS = "pcs"
    TBSP = "tbsp"
    TSP = "tsp"
    PINCH = "pinch"
    TO_TASTE = "to_taste"


def _pg_enum(python_enum: type[enum.Enum], name: str) -> SAEnum:
    """Build a native PostgreSQL ENUM that stores `.value` (e.g. "easy"), not the
    Python member `.name` (e.g. "EASY") — SQLAlchemy defaults to the latter.
    """
    return SAEnum(python_enum, name=name, values_callable=lambda obj: [e.value for e in obj])


def _uuid_pk() -> Mapped[uuid.UUID]:
    """Shared primary-key column factory.

    UUIDs are generated in Python (uuid.uuid4), not by the database, so ids exist
    before a row is even flushed — useful when the app needs the id right after
    building an object, e.g. to publish a Kafka event with it later.
    """
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


# Auth


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    recipes: Mapped[list["Recipe"]] = relationship(back_populates="author")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(back_populates="user")
    ratings: Mapped[list["Rating"]] = relationship(back_populates="user")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Only the hash of the token is stored — same principle as passwords: if the
    # database leaks, the tokens themselves still can't be extracted from it.
    token_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime.datetime]
    # NULL while the token is still valid; set to "now" on logout to revoke it
    # without deleting the row (keeps an audit trail of past sessions).
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


# Reference tables (dictionaries)


class RecipeCategory(Base):
    __tablename__ = "recipe_categories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True)

    recipes: Mapped[list["Recipe"]] = relationship(back_populates="category")


class IngredientCategory(Base):
    __tablename__ = "ingredient_categories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(100), unique=True)

    ingredients: Mapped[list["IngredientCatalog"]] = relationship(back_populates="category")


class IngredientCatalog(Base):
    """The master list of known ingredients.

    A recipe never stores an ingredient name directly — it points here via
    RecipeIngredient, so the same ingredient is never spelled two different
    ways across different recipes.
    """

    __tablename__ = "ingredients_catalog"

    id: Mapped[uuid.UUID] = _uuid_pk()
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredient_categories.id"))
    name: Mapped[str] = mapped_column(String(150), unique=True)

    category: Mapped["IngredientCategory"] = relationship(back_populates="ingredients")


class Tag(Base):
    """Free-form labels (e.g. "vegetarian", "quick"), many-to-many with recipes.

    Unlike RecipeCategory (exactly one per recipe), a recipe can have any
    number of tags — see recipe_tags below.
    """

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(50), unique=True)


# Plain association table (no extra columns of its own), so a lightweight
# sa.Table is enough — no need for a full ORM class like the other models.
recipe_tags = Table(
    "recipe_tags",
    Base.metadata,
    Column("recipe_id", ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


# Recipes


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipe_categories.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(default=None)
    cooking_time_minutes: Mapped[int]
    difficulty: Mapped[Difficulty] = mapped_column(_pg_enum(Difficulty, "difficulty_enum"))
    servings: Mapped[int]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    author: Mapped["User"] = relationship(back_populates="recipes")
    category: Mapped["RecipeCategory"] = relationship(back_populates="recipes")
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship(secondary=recipe_tags)
    ratings: Mapped[list["Rating"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    """One line of a recipe's ingredient list: which ingredient, how much, in what unit."""

    __tablename__ = "recipe_ingredients"

    id: Mapped[uuid.UUID] = _uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients_catalog.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit: Mapped[MeasurementUnit] = mapped_column(_pg_enum(MeasurementUnit, "measurement_unit"))
    # Preserves the order ingredients were listed in when the recipe was authored.
    position: Mapped[int]

    recipe: Mapped["Recipe"] = relationship(back_populates="ingredients")
    ingredient: Mapped["IngredientCatalog"] = relationship()


# Ratings & comments


class Rating(Base):
    """One user's rating of one recipe.

    UniqueConstraint(recipe_id, user_id) is what enforces "one rating per user
    per recipe" at the database level — changing a rating is an UPDATE of this
    same row (upsert), not a new row.
    """

    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("recipe_id", "user_id", name="uq_rating_per_user_recipe"),
        CheckConstraint("value >= 1 AND value <= 5", name="ck_rating_value_range"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    value: Mapped[int]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    recipe: Mapped["Recipe"] = relationship(back_populates="ratings")
    user: Mapped["User"] = relationship(back_populates="ratings")
    comment: Mapped["RatingComment | None"] = relationship(
        back_populates="rating", cascade="all, delete-orphan", uselist=False
    )


class RatingComment(Base):
    """The comment attached to a rating — a 1:1 relationship, enforced by unique=True
    on rating_id below (at most one comment per rating).
    """

    __tablename__ = "rating_comments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    rating_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ratings.id", ondelete="CASCADE"), unique=True
    )
    text: Mapped[str]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    rating: Mapped["Rating"] = relationship(back_populates="comment")


# Search logs


class SearchLog(Base):
    """One row per search query."""

    __tablename__ = "search_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    query_text: Mapped[str | None] = mapped_column(default=None)
    # Filters are stored as JSONB rather than a fixed set of columns because the
    # filter shape can grow (new facets) without a schema migration every time.
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    results_count: Mapped[int]
    took_ms: Mapped[int]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
