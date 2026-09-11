"""FastAPI application entry point — wires up the GraphQL router."""

import os

import strawberry
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from strawberry.fastapi import GraphQLRouter

from schema import schema

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_async_engine(DATABASE_URL, echo=False)


@strawberry.type
class Query:
    @strawberry.field
    def hello(self) -> str:
        """Check that the API is responding."""
        return "RecipeGraph API is alive"

    @strawberry.field
    async def health(self) -> str:
        """Checks the actual connection to Postgres."""
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "postgres: ok"


graphql_app = GraphQLRouter(schema)

app = FastAPI(title="RecipeGraph API")
app.include_router(graphql_app, prefix="/graphql")


@app.get("/")
def root():
    return {"status": "ok", "graphql": "/graphql"}
