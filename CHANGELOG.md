# Changelog

## [0.1.7] - 2026-09-20

### Added
- **Automated Test Suite (`tests/`):**
  - Added unit and regression tests for DSN URL-encoding logic in `db.py` (handling passwords with special characters like `@`, `:`, `/`, `#`).
  - Added schema constraint validation tests: unique constraints (`User.username`, `User.email`, `RecipeCategory.name`, `IngredientCategory.name`, `IngredientCatalog.name`, `Tag.name`), composite rating constraint (one rating per user per recipe), 1:1 constraint for rating comments, and check constraint for rating values (`1-5`).
  - Added ENUM persistence verification confirming PostgreSQL stores lowercase values matching `values_callable` mapping.
  - Test suite configured to execute against disposable database (`recipes_test_db`) with automatic table truncation (`TRUNCATE`) between test runs.
  - Configured `pythonpath = app` in `pytest.ini` for clean module resolution across application imports.

### Refactored
- **Project Structure Reorganization:**
  - Restructured project layout to follow Python best practices: moved `tests/` from `app/` to the repository root.

## [0.1.6] - 2026-09-14

### Added
- **Structured JSON Logging (`logging_config.py`):**
  - Integrated `structlog` configured for JSON output across the application.
- **GraphQL Exception Handling Extension (`app/schema.py` / `ErrorLoggingExtension`):**
  - Added Strawberry `ErrorLoggingExtension` to log every resolver exception with full tracebacks.
  - Implemented exception masking: safe business exceptions (`InvalidCredentialsError`, `NotAuthenticatedError`, etc.) pass through to the client unchanged, while unexpected errors are masked as a generic `"Internal server error"`.
- **Exception Tracking with Sentry (`sentry_config.py`):**
  - Added Sentry integration reading from `SENTRY_DSN` (silently disabled when unset).
  - Added `SENTRY_DSN` to `.env.example` and `docker-compose.yml`.

## [0.1.5] - 2026-09-13

### Added
- **Per-Request Auth Context (`context.py`):**
  - Added Strawberry `get_context` getter to extract `Authorization: Bearer <token>`, verify JWT, and populate user context via `info.context["user"]`.
  - Graceful degradation for unauthenticated or malformed/expired token requests (`user = None`) without failing entire public GraphQL operations.
  - Reusable `require_user(info)` helper raising `NotAuthenticatedError` for protected GraphQL resolvers.
  - Added `currentUser` GraphQL query returning authenticated user profile or `null`.

## [0.1.4] - 2026-09-12

### Added
- **GraphQL Session Management Mutations (`app/schema.py`):**
  - Added `refreshToken` mutation: validates refresh tokens by SHA-256 hash (checking existence, expiration, and revocation status) and returns a new access token.
  - Added `logout` mutation: revokes refresh tokens by setting `revoked_at`. Designed to be idempotent (re-logging-out an already-revoked token returns `true`, non-existent token returns `false`).
  - Added unified generic error messaging (`"Invalid or expired refresh token"`) across refresh failures to prevent sensitive status leaks, consistent with authentication security practices in #6.

### Refactored
- Extracted `hash_refresh_token` helper function from `create_refresh_token` in `app/auth.py` to ensure consistent SHA-256 hashing logic across token creation, lookup, and revocation.

## [0.1.3] - 2026-09-11

### Added
- **Authentication System (`app/auth.py`):**
  - Password hashing via `argon2id` using `passlib`.
  - Short-lived JWT access tokens (15 min lifespan) with stateless verification.
  - Opaque random refresh tokens (`secrets.token_urlsafe`), persisted in `refresh_tokens` table via SHA-256 hashes to support revocation/logout.
- **GraphQL Schema (`app/schema.py`):**
  - Moved GraphQL schema into a dedicated module `app/schema.py`.
  - Added `register` and `login` GraphQL mutations.
  - Added `AuthPayload` and `User` GraphQL types.
  - Unified error response for `login` mutation to prevent user enumeration attacks.
  - Unique-constraint violation handling for duplicate email/username during registration with clean GraphQL error responses.

## [0.1.2] - 2026-09-09

### Added
- Reference data seeding script (`app/seed.py`) with 42 recipe categories, 15 ingredient categories, and 260+ base ingredients.
- Idempotent insert mechanism using PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` on unique constraints.
- Foreign key resolution helper (`get_or_create_ingredient_category`) for safe category assignment.

## [0.1.1] - 2026-09-08

### Added
- SQLAlchemy models for the full data schema (12 tables) — `app/models.py`
- Initial Alembic migration, plus a follow-up migration making all timestamp
  columns timezone-aware (`TIMESTAMPTZ` instead of `TIMESTAMP`)
- `app/db.py` — shared async engine/session factory, single source of truth
  for the database connection string
- `MIGRATIONS.md` — guide to how migrations work in this project, how the
  existing ones came about, and how to create new ones

### Fixed
- Database passwords containing reserved URL characters (e.g. `@`) no longer
  break connection parsing. `asyncpg`'s DSN parser splits on the *first* `@`
  rather than the last, which previously produced a confusing
  "Name or service not known" error that looked like a DNS/networking issue
  but wasn't. `db.py` now URL-encodes credentials via
  `urllib.parse.quote_plus()` before building the connection string.
- Alembic migrations no longer route the connection URL through its
  `configparser`-backed `Config` object — that layer treats `%` as the start
  of its own interpolation syntax and corrupted percent-encoded credentials
  (`%40` etc.) on read-back. The URL is now passed directly to the engine.
- `Dockerfile` and `requirements.txt` moved to the repository root (were
  previously inside `app/`, which broke the Docker build context).
- Local data directories are now namespaced under
  `${DB_DATA_PATH}/recipegraph/...`, so a shared `DB_DATA_PATH` across
  multiple local projects no longer collides.

### Known issues
- `pghero` is temporarily disabled — crashes on boot with an unresolved
  Zeitwerk `eager_load` error, reproducible on two different image versions.
  Not blocking: Grafana/Prometheus already cover Postgres monitoring. Tracked
  as `v0.4.2` in `ROADMAP.md`.

## [0.1.0] - 2026-09-03

### Added
- Project infrastructure: docker-compose (Postgres, Kafka, Elasticsearch, monitoring)
- FastAPI + Strawberry API boilerplate with live-reload
