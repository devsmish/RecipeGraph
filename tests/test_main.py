"""Smoke tests for the app entry point (main.py)."""

from conftest import graphql_request


async def test_root_endpoint(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "graphql": "/graphql"}


async def test_hello_and_health_queries(client):
    # `health` runs a real SELECT 1 through db.py's engine — the only engine in the app.
    res = await graphql_request(client, "query { hello health }")
    assert res["data"] == {"hello": "RecipeGraph API is alive", "health": "postgres: ok"}
