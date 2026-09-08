"""Shared async database engine and session factory.

Centralized here so the running app (main.py) and one-off scripts (seed.py) use the
same engine configuration instead of each creating its own connection pool.
"""

import os
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _build_database_url() -> str:
    """Build the connection URL from separate POSTGRES_* env vars, URL-encoding the
    username and password.

    Not just string interpolation: credentials can legitimately contain characters
    that are reserved delimiters in a URL ("@", ":", "/", "%", "#") — an unencoded "@"
    in a password, for example, gets misread as the userinfo/host separator by
    asyncpg's own DSN parser (it splits on the *first* "@", not the last), producing a
    garbage hostname and a confusing "Name or service not known" error that has
    nothing to do with DNS or networking. quote_plus() escapes exactly these
    characters, so the resulting URL is unambiguous no matter what the password is.

    An explicit DATABASE_URL env var still wins if set — e.g. for one-off overrides —
    on the assumption that whoever sets it directly has already encoded it correctly.
    """
    explicit_url = os.environ.get("DATABASE_URL")
    if explicit_url:
        return explicit_url

    user = quote_plus(os.environ["POSTGRES_USER"])
    password = quote_plus(os.environ["POSTGRES_PASSWORD"])
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db_name = os.environ["POSTGRES_DB"]

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db_name}"


DATABASE_URL = _build_database_url()

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
