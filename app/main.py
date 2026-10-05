"""FastAPI application entry point — wires up the GraphQL router."""

from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from context import get_context
from logging_config import configure_logging
from schema import schema
from sentry_config import configure_sentry

configure_logging()
configure_sentry()

graphql_app = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI(title="RecipeGraph API")
app.include_router(graphql_app, prefix="/graphql")


@app.get("/")
def root():
    return {"status": "ok", "graphql": "/graphql"}
