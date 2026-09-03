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

## Contributing / branching model

`main` and `develop` are protected — all work happens on `feature/<issue-number>-<slug>` branches
merged into `develop` via PR, releases go through `release/vX.Y.Z`.

## Project status

Early stage — infrastructure and design are in place, application code is in progress.
Full scope, data model, and a step-by-step build app.

## License

[MIT](./LICENSE)
