# Changelog

# Changelog

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
