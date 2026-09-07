"""Alembic environment configuration.

Uses the async SQLAlchemy engine (asyncpg driver) so migrations run through the same
kind of connection the application itself uses — no separate sync driver to install
or keep in sync.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from db import DATABASE_URL
from models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata is what `alembic revision --autogenerate` diffs the live
# database against for *future* migrations.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without connecting to a database (`alembic upgrade --sql`)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect to the real database and apply migrations (the normal case)."""
    connectable = async_engine_from_config(
        {"sqlalchemy.url": DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
