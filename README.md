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
see `postgres/init.sql`), never against dev data:

```bash
docker compose exec -e POSTGRES_DB=recipes_test_db api pytest -v
```

## Contributing / branching model

`main` and `develop` are protected — all work happens on `feature/<issue-number>-<slug>` branches
merged into `develop` via PR, releases go through `release/vX.Y.Z`.

## Project status

Early stage. Data models, database schema, and reference data seeding (recipe categories, ingredient categories, master 
ingredient list) are fully in place. GraphQL API surface (queries and mutations beyond the health check) is still to 
come. Full scope, data model, and a step-by-step build roadmap.

## License

[MIT](./LICENSE)
