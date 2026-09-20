"""Shared pytest fixtures.

Tests run against a real PostgreSQL database (not SQLite) — the schema uses
Postgres-specific features (native ENUM types, UUID, JSONB) that SQLite can't
represent. db.py builds its connection URL at import time, so POSTGRES_DB must
already point at the test database (`recipes_test_db`) before pytest imports
anything.
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest-only")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from db import DATABASE_URL, engine  # noqa: E402
from models import Base  # noqa: E402

# Tests TRUNCATE every table between runs (see _clean_tables below) — a real safety
# net, not a formality: if this ever pointed at dev data, running the suite would
# silently wipe it. Checked here (after importing db.py) rather than reading the env
# var directly, since the actual connection string is now built from separate
# POSTGRES_* components, not a single pre-assembled DATABASE_URL.
if "test" not in DATABASE_URL:
    raise RuntimeError(
        "The database this test run would connect to doesn't look like a test "
        "database (expected 'test' in the name) — refusing to run, since this test "
        "suite TRUNCATEs every table.\n"
        "Run pytest with POSTGRES_DB pointing at the disposable test database:\n"
        "  docker compose exec -e POSTGRES_DB=recipes_test_db api pytest"
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _tables():
    """Create every table once per test session, drop them all when the session ends."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Truncate every table after each test so tests never leak data into one another."""
    yield
    async with engine.begin() as conn:
        table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {table_names} CASCADE"))


@pytest_asyncio.fixture
async def client():
    """An HTTP client wired directly to the ASGI app — no real server/port needed."""
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def graphql_request(client, query: str, variables: dict | None = None, token: str | None = None):
    """Small helper so test bodies don't repeat the POST/headers boilerplate."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = await client.post(
        "/graphql", json={"query": query, "variables": variables or {}}, headers=headers
    )
    return response.json()
