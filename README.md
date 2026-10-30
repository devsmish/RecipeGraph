# RecipeGraph

A recipe catalog with full-text and faceted search — built as a learning project to practice
**GraphQL, event-driven architecture, and search infrastructure** end to end, not just CRUD.

> Recipes are the domain; the point of the project is the system behind them.

## Why this project exists

Most "GraphQL + Postgres" portfolio projects stop at CRUD. RecipeGraph is deliberately scoped to
exercise the parts of a real search system that CRUD tutorials skip:

- **GraphQL done properly** — code-first schema, async resolvers, and the N+1 problem solved with
  `DataLoader` instead of blindly eager-loading everything
- **Two sources of truth, one consistency model** — PostgreSQL owns the data, Elasticsearch owns
  search relevance and facets; the project explicitly deals with *eventual consistency* between
  them instead of pretending it doesn't exist
- **Event-driven sync, not a cron job** — writes to Postgres publish events to Kafka; a consumer
  keeps the search index up to date, independently and idempotently
- **Failure handling as a first-class concern** — retry with backoff/jitter for search reads, a
  dead-letter topic for events that can't be processed, and an explicit (documented) decision
  *not* to auto-retry writes without an idempotency key
- **Observability from day one** — `pg_stat_statements`, Prometheus + Grafana, and pgHero are
  part of the stack, not an afterthought bolted on later
- **Authentication & Security** — Argon2id password hashing, stateless short-lived JWT access tokens, 
  and opaque hashed refresh tokens for secure session revocation without security leaks (user 
  enumeration prevention).

## Tech stack

| Layer        | Technology                                                    |
|--------------|---------------------------------------------------------------|
| API          | FastAPI                                                       |
| GraphQL      | Strawberry (code-first, async)                                |
| Database     | PostgreSQL 16 + SQLAlchemy 2.0 (async) + Alembic              |
| Search       | Elasticsearch 8.x                                             |
| Event bus    | Kafka (KRaft mode) + aiokafka                                 |
| Auth         | Argon2id/bcrypt password hashing, JWT access + refresh tokens |
| Monitoring   | Prometheus, Grafana, postgres_exporter, pgHero                |
| Logging      | Sentry, structlog                                             |
| Infra        | Docker Compose                                                |

## Getting started

```bash
cp .env.example .env 
docker compose up -d
```

## Common commands

### Docker Compose

```bash
docker compose up -d                    # start the full stack in the background
docker compose up -d --force-recreate api   # recreate just the api container (e.g. after an .env change)
docker compose build --no-cache api     # rebuild the api image from scratch (e.g. after Dockerfile/requirements.txt changes)
docker compose ps                       # status of every service
docker compose logs -f api              # follow logs for one service
docker compose down                     # stop and remove containers (data on disk is untouched — bind-mounted, not a Docker volume)
```

### Migrations (Alembic)

Full explanation of how this works and how the existing migrations came:

```bash
docker compose exec api alembic upgrade head                          # apply all pending migrations
docker compose exec api alembic revision --autogenerate -m "message"  # generate a new migration from models.py changes
docker compose exec api alembic downgrade -1                          # roll back the last migration
docker compose exec api alembic current                               # show the currently applied revision
```

### Tests

Tests run against a separate, disposable database (`recipes_test_db`, created automatically —
see `postgres/init.sql`), never against dev data. Run them inside the `api` container:

```bash
docker compose exec -w / -e POSTGRES_DB=recipes_test_db api pytest -v
```

`-w /` runs pytest from the container root, where `pytest.ini`, `tests/` and `app/` sit side by side,
as in the repo. Plain `pytest` on the host fails with `KeyError: 'POSTGRES_USER'`, because the database
settings come from the container's environment. `tests/` and `pytest.ini` are mounted into the container
by `docker-compose.yml`; after changing the compose file recreate the container with
`docker compose up -d api`.

#### Writing tests

Test data comes from async factories in `tests/factories.py`. Each one writes its row to the test database,
commits and returns the model. Anything you don't pass gets a valid default, and the objects it depends on are
created for you, so a test spells out only what it cares about:

```python
async def test_my_recipes(auth_gql, user):
    await create_recipe(author=user, title="Soup", ingredients=[tomato], tags=[vegan])

    result = await auth_gql("query { myRecipes { title } }")
```

Available factories: `create_user`, `create_recipe_category`, `create_ingredient_category`, `create_ingredient`,
`create_tag`, `create_recipe` (with ingredient lines and tags), `create_rating` (with an optional comment) and
`access_token_for(user)`. Fixtures from `tests/conftest.py`: `user`, `token`, `gql` (anonymous, or `token=` for
another user), `auth_gql` (authenticated as `user`), `client` and `sentry_calls`.

## API errors

GraphQL errors fall into three groups, and the group decides what the client sees:

**Expected errors** — subclasses of `PublicError` (`app/errors.py`). The message is written for the client and
is returned as is. They are logged at WARNING and are not sent to Sentry.

| Situation | Message |
|---|---|
| Protected operation without a valid access token | `Authentication required` |
| `register` with a username or email that already exists | `Username or email is already taken` |
| `login` with a wrong email or password | `Invalid email or password` |
| `refreshToken` with an unknown, revoked or expired token | `Invalid or expired refresh token` |
| Recipe does not exist (also: recipe deleted while it was being rated) | `Recipe not found` |
| Updating or deleting someone else's recipe | `You can only modify your own recipes` |
| `rateRecipe` with a value outside 1–5 | `Rating value must be between 1 and 5` |
| An ID argument that is not a UUID | `Invalid ID for "<field>": expected a UUID` |
| `createRecipe` / `updateRecipe` with a category that does not exist | `Recipe category not found` |
| `createRecipe` / `updateRecipe` with an ingredient that does not exist | `Ingredient not found` |
| `createRecipe` / `updateRecipe` with a tag that does not exist | `Tag not found` |

The "invalid ID" message names the exact argument (`id`, `categoryId`, `ingredients[1].ingredientId`,
`tagIds[0]`, `recipeId`) and never echoes the value that was sent.

**GraphQL-level errors** — syntax errors, unknown fields, missing variables. They have no underlying exception and
the message is generated from the client's own query, so they pass through unchanged (WARNING, no Sentry).

**Unexpected errors** — bugs, database failures, anything that is not a `PublicError`. The client only gets
`Internal server error` (the field `path` is kept); the full details are logged at ERROR and sent to Sentry, so
internals such as SQL or file paths never leak into a response.

To add a new client-visible error, subclass `PublicError` — there is no list to keep in sync.

## Contributing / branching model

`main` and `develop` are protected — all work happens on `feature/<issue-number>-<slug>` branches
merged into `develop` via PR, releases go through `release/vX.Y.Z`.

## Project status

Active development. Core database schema, reference data seeding, complete auth system (Argon2id, JWT, 
opaque refresh tokens), session GraphQL mutations (`register`, `login`, `refreshToken`, `logout`), auth 
context, `currentUser` query, structured JSON logging (`structlog`), Sentry error tracking, Strawberry 
exception masking, test coverage with shared test factories and fixtures, read queries for 
recipes/dictionaries, full recipe management mutations  (`createRecipe`, `updateRecipe`, `deleteRecipe`), 
`rateRecipe` mutation with rating/comment upserts and rating value validation (1–5), per-request 
DataLoaders solving the N+1 query problem, cleaned up application startup architecture, strict GraphQL 
exception masking via `ErrorLoggingExtension` and `PublicError`, **and explicit client-side UUID validation 
with clean error messages (`InvalidIdError`)** are fully implemented.

## License

[MIT](./LICENSE)
