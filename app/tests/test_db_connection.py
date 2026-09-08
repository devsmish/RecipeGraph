"""Tests for database connection URL construction and connectivity.

This file exists specifically because of a real bug found while setting up the
project: a password containing '@' broke asyncpg's DSN parsing (it splits on the
*first* '@', not the last), producing a confusing "Name or service not known" error
that looked like a DNS/networking problem but had nothing to do with either. These
tests guard against that regression and confirm the app can actually reach Postgres.
"""

import pytest

from db import _build_database_url, engine


@pytest.mark.parametrize(
    "password",
    [
        "simple",
        "has@symbol",  # the exact character that caused the original bug
        "has:colon",
        "has/slash",
        "has%percent",
        "has space",
        "has#hash",
    ],
)
def test_database_url_encodes_special_characters_in_password(monkeypatch, password):
    monkeypatch.setenv("POSTGRES_USER", "testuser")
    monkeypatch.setenv("POSTGRES_PASSWORD", password)
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "recipes_test_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url = _build_database_url()

    # Exactly one *unescaped* "@" should remain in the URL —
    # the real userinfo/host separator.
    assert url.count("@") == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_can_actually_connect_to_the_database():
    """An explicit, clearly-named connectivity smoke test.
    This test exists so a broken connection points straight at
    itself instead.
    """
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql("SELECT 1")
        assert result.scalar() == 1
