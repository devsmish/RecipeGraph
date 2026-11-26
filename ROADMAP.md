# RecipeGraph — Roadmap

What has already shipped is recorded in [CHANGELOG.md](CHANGELOG.md); this file is the plan.

## Versioning convention

`MAJOR.MINOR.PATCH`:
- **MINOR** — a theme: a coherent chunk of functionality (e.g. `0.2` = "Core GraphQL CRUD")
- **PATCH** — a task within that theme; each task = one GitHub Issue = one `feature/*` branch
  = one PR into `develop`

Example: `v0.2.3` = theme `0.2`, task number 3 in it.

Each task gets its own GitHub Issue before work starts (per `WORKFLOW.md`). Issue numbers are listed
in the tables below for traceability.

## Releases and tags

Every task is released on its own: when its PR is merged into `develop`, a `release/vX.Y.Z` branch is
merged into `main` and tagged. **The tag is the task label** — task `v0.2.8` ships as git tag `v0.2.8`,
and its entry in [CHANGELOG.md](CHANGELOG.md) is headed `[0.2.8]`. There is no separate "release number"
to translate to.

The project started with `v0.1.0` (project scaffolding, issue #5). Task labels of a theme are assigned in
order as the tasks are created: theme `v0.2` started at `v0.2.0`, and labels of later themes in this file
are provisional until their first task is created.

## Documentation convention: GraphQL schema descriptions

GraphQL is self-documenting via introspection — there's no separate "generate docs" step like
OpenAPI/Swagger. Every type, field, and argument added from theme `v0.2` onward must include a
`description=` (Strawberry) so the built-in GraphiQL docs panel stays useful without extra effort.
This isn't a standalone task — it's a rule applied while writing every resolver.

---

## Theme v0.1 — Foundation & Auth

Data layer and authentication — nothing works without this, and it's safer to get the schema
and security basics right before building features on top of them.

| Task | Title | Depends on | Issue | Status |
|---|---|---|---|---|
| **v0.1.1** | SQLAlchemy models + first Alembic migration for the full schema | — | #2 | Released |
| **v0.1.2** | Seed script: fill reference tables (recipe categories, ingredient categories, sample ingredients) | v0.1.1 | #3 | Released |
| **v0.1.3** | Password hashing (argon2id) + `register`/`login` mutations, `AuthPayload` type | v0.1.1 | #11 | Released |
| **v0.1.4** | Refresh tokens: `refresh_tokens` table logic, `refreshToken`/`logout` mutations | v0.1.3 | #15 | Released |
| **v0.1.5** | Auth context in resolvers: extract & verify access token, expose `currentUser` | v0.1.3 | #19 | Released |
| **v0.1.6** | Structured logging (`structlog`) + Strawberry error-handling extension + Sentry integration | v0.1.1 | #23 | Released |
| **v0.1.7** | Test infrastructure: disposable test database, DSN URL-encoding and schema-constraint tests; `tests` moved to the repository root | v0.1.1 | #27 | Released |
| **v0.1.8** | Tests for the auth system and for the seed script | v0.1.2, v0.1.3–v0.1.5 | #28 | Released |

Also part of the initial setup, without a task label: moving DB/Grafana credentials from hardcoded values to
`.env` (issue #4).

---

## Theme v0.2 — Core GraphQL CRUD

Basic read/write GraphQL API over PostgreSQL only — no search yet, that's theme v0.3. The second half of this
theme is hardening: tests, CI, cleanup and refactoring before search is built on top.

| Task | Title | Depends on | Issue | Status |
|---|---|---|---|---|
| **v0.2.0** | Read queries: `recipe(id)`, `myRecipes`, dictionary queries (categories, ingredients) | v0.1.5 | #34 | Released |
| **v0.2.1** | Mutations: `createRecipe`, `updateRecipe`, `deleteRecipe` | v0.2.0 | #37 | Released |
| **v0.2.2** | `rateRecipe` mutation — upsert rating + comment logic | v0.2.1 | #40 | Released |
| **v0.2.3** | `DataLoader` for nested fields (`author`, `ingredients`, `category`, `tags`, `ratings`) — fixes N+1 | v0.2.0 | #43 | Released |
| **v0.2.4** | Remove the duplicate DB engine and dead `Query` from `main.py` | — | #46 | Released |
| **v0.2.5** | Make `pytest` runnable inside the `api` container | — | #49 | Released |
| **v0.2.6** | `PublicError` base class; attach `ErrorLoggingExtension` to the schema | v0.1.6 | #52 | Released |
| **v0.2.7** | Clear error for malformed UUID arguments (`parse_uuid`) | v0.2.6 | #55 | Released |
| **v0.2.8** | `rateRecipe`: validate the rating value, map only known database errors | v0.2.2, v0.2.6 | #56 | Released |
| **v0.2.9** | Shared test factories and fixtures | — | #57 | Released |
| **v0.2.10** | Tests for recipe queries and CRUD mutations (and clear errors for unknown category, ingredient and tag IDs) | v0.2.9 | #58 | Released |
| **v0.2.11** | Tests for `rateRecipe` | v0.2.8, v0.2.9 | #59 | Released |
| **v0.2.12** | CI: run `ruff` and `pytest` on every pull request | — | #60 | Released |
| **v0.2.13** | Documentation and repository housekeeping (this file, line endings, UTF-8 `requirements.txt`) | — | #61 | Released |
| **v0.2.14** | Refactor: split `recipes.py` into a package | v0.2.10–v0.2.12 | #62 | Released |
| **v0.2.15** | Refactor: split auth code into a package | v0.2.14 | #63 | Planned |
| **v0.2.16** | Typed GraphQL context and central configuration (`config.py`) | v0.2.14, v0.2.15 | #64 | Planned |
| **v0.2.17** | `updateRecipe`: reject an explicit `null` for required fields | v0.2.14 | | Planned |
| **v0.2.18** | Ingredient search: escape `%` and `_` in the search term | v0.2.14 | | Planned |
| **v0.2.19** | `myRecipes`: return recipes in a defined order | v0.2.14 | | Planned |

---

## Theme v0.3 — Elasticsearch Search

Full-text and faceted search — the main technical showcase of the project.

| Task | Title | Depends on |
|---|---|---|
| **v0.3.1** | Elasticsearch index mapping + manual sync call from mutation resolvers | v0.2.1 |
| **v0.3.2** | `searchRecipes` resolver: full-text query + facet aggregations | v0.3.1 |
| **v0.3.3** | Retry policy for search reads (backoff + jitter, `SearchUnavailableError`) | v0.3.2 |
| **v0.3.4** | `search_logs` table — log every search query | v0.3.2 |
| **v0.3.5** | Cursor-based pagination (Relay-style connections) for `searchRecipes` | v0.3.2 |

---

## Theme v0.4 — Observability

Making the running system legible — metrics, dashboards, and how to read them.

| Task | Title | Depends on |
|---|---|---|
| **v0.4.1** | Import Grafana dashboard (ID 9628); document how to read key metrics | v0.1.1 |
| **v0.4.2** | *(known issue)* pgHero crashes on boot with a Zeitwerk `eager_load` error — reproducible on both `v3.7.0` and `v4.0.0`, root cause not yet identified. Currently disabled (commented out) in `docker-compose.yml`. Not blocking — Grafana/Prometheus already cover Postgres monitoring. | — |

---

## Theme v0.5 — Event-driven Architecture (Kafka)

Decoupling PostgreSQL and Elasticsearch through an event bus — the second major showcase.

| Task | Title | Depends on |
|---|---|---|
| **v0.5.1** | Kafka producer: publish `recipe.*` events on mutation instead of calling ES directly | v0.3.1 |
| **v0.5.2** | Kafka consumer: idempotent ES index updates from the `recipe-events` topic | v0.5.1 |
| **v0.5.3** | Dead Letter Topic handling for messages the consumer can't process | v0.5.2 |

---

## Theme v0.6 — External Access (Reverse Proxy)

Right now every service in the stack exposes its own port directly — fine for local development,
but not something you'd want to expose as-is beyond `localhost` (Elasticsearch and Kafka have no
auth configured, for instance). A reverse proxy in front of the API is the standard fix.

| Task | Title | Depends on |
|---|---|---|
| **v0.6.1** | Add `nginx` service as reverse proxy in front of `api` — single entry point on port 80, `/graphql` routed to `api`; other services (Postgres, ES, Kafka, admin UIs) stay internal-only, no longer bound to host ports | v0.1.1 |
| **v0.6.2** | Basic nginx rate limiting on `/graphql` — an extra layer on top of the app-level retry policy from SPEC.md §9.1 | v0.6.1 |

---

## Theme v1.0 — Stretch Goals (optional, post-MVP)

Not required for the portfolio version — pick and choose based on what's still interesting once
the core system works end to end.

| Task | Title | Depends on |
|---|---|---|
| **v1.0.1** | Debezium (CDC) instead of the manual Kafka producer | v0.5.2 |
| **v1.0.2** | GraphQL Subscriptions — live search result updates | v0.3.2 |
| **v1.0.3** | Field-level authorization (e.g. drafts visible only to their author) | v0.1.5 |
| **v1.0.4** | Avro + Schema Registry instead of plain JSON in Kafka messages | v0.5.1 |
| **v1.0.5** | Refresh token rotation (new refresh token issued on every use) | v0.1.4 |
| **v1.0.6** | Idempotency key support for write mutations (safe retry for `createRecipe` etc.) | v0.2.1 |
| **v1.0.7** | Search logs via Kafka → dedicated Elasticsearch analytics index | v0.5.1, v0.3.4 |
| **v1.0.8** | Ship structured app logs to Elasticsearch, view via Kibana; standalone GraphQL docs site (SpectaQL) | v0.1.6 |
| **v1.0.9** | HTTPS via self-signed cert (e.g. `mkcert`) terminated at nginx, for local HTTPS practice | v0.6.1 |

---

## How each task is worked

1. Draft the GitHub Issue (title + description + acceptance criteria)
2. Create the Issue on GitHub; its number goes into the tables above
3. Branch: `git checkout -b feature/<issue-number>-<slug>` from `develop`
4. Implementation, with tests, a `CHANGELOG.md` entry and (if behavior or commands change) a README update;
   `ruff check .` and `pytest` must pass — CI runs both on every pull request
5. PR into `develop` with `Closes #<issue-number>`
6. Release: `release/vX.Y.Z` branch into `main`, tag `vX.Y.Z`, GitHub Release notes
