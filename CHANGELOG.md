# Changelog

All notable changes to this project will be documented in this file.

## [0.2.9] - 2026-10-26

### Added
- `../tests/factories.py`: async factories for test data — users, recipe and ingredient categories, ingredients, tags, recipes (with ingredient lines and tags) and ratings (with optional comments) — plus `access_token_for(user)`. Defaults are complete and valid, dependencies are created on demand, and unique values come from a counter, so factories never collide.
- Shared fixtures in `../tests/conftest.py`: `user`, `token`, `gql` (anonymous or with `token=`), `auth_gql` (authenticated as `user`) and `sentry_calls` (previously copied into three test files).
- `../tests/test_factories.py`: unique defaults, a complete recipe from no arguments, ingredient order/amounts/units, tags, ratings with comments, and the token/`gql`/`auth_gql` fixtures.

### Changed
- `test_dataloaders.py`, `test_models.py`, `test_invalid_ids.py`, `test_rate_recipe_validation.py` and `test_error_handling.py` use the shared factories and fixtures instead of hand-built rows and local copies of the same fixtures. What they assert is unchanged.
- No application code changes.

---

## [0.2.8] - 2026-10-23

### Fixed
- **`rateRecipe` treated every database integrity error as "Rating value must be between 1 and 5".** The 1–5 range was only enforced by the CHECK constraint, and the resolver wrapped `flush()` in `except IntegrityError` → `InvalidRatingValueError`. So other failures were mislabelled: for example a recipe deleted between the existence check and the INSERT (foreign key violation) was reported to the client as an invalid rating value.

### Changed
- The rating value is validated in the resolver (`MIN_RATING_VALUE` / `MAX_RATING_VALUE`) before any database work; out-of-range values no longer cause a query. The CHECK constraint stays as a safety net.
- Integrity errors from saving a rating are mapped by PostgreSQL error code and constraint name (`_map_rating_integrity_error`): the range CHECK (`ck_rating_value_range`) → `InvalidRatingValueError`; a foreign key violation on the recipe → `RecipeNotFoundError`. Anything else (for example a unique violation from a concurrent first rating by the same user) propagates as an unexpected error: masked as "Internal server error", logged at ERROR and reported to Sentry.

### Added
- `../tests/test_rate_recipe_validation.py`: out-of-range values (0, 6, -1, 100, -100) rejected without touching `recipes`/`ratings`; boundary values 1 and 5 accepted; the CHECK-constraint path (resolver range widened so the value reaches the database); recipe deleted after the lookup → `Recipe not found`; concurrent unique violation → unexpected error, reported to Sentry, not mislabelled. The two race conditions are simulated deterministically by running an action right after the resolver's rating lookup.

### Known gap
- Two simultaneous *first* ratings by the same user on the same recipe: the second one now fails with "Internal server error" (unique violation) instead of being turned into an update. Handling it (retry as an update) is not part of this task.

---

## [0.2.7] - 2026-10-19

### Fixed
- **A malformed ID argument produced "Internal server error"**, an ERROR log line and a Sentry report. Recipe operations convert client-supplied IDs with `uuid.UUID(...)`, which raises `ValueError` on input like `recipe(id: "abc")`; since 0.2.6 that counts as an unexpected error. It is a client mistake, so the client now gets `Invalid ID for "id": expected a UUID` (naming the exact field), it is logged at WARNING and is not sent to Sentry.
- **`createRecipe` / `updateRecipe` validate every ID before touching the database**, so a bad ID can no longer be noticed after the recipe row has already been inserted (`updateRecipe` also no longer applies earlier field changes before failing on a later ID).

### Added
- `../app/ids.py`: `parse_uuid(value, field_name)` and `InvalidIdError` (a `PublicError`). The message names the GraphQL field (`categoryId`, `ingredients[1].ingredientId`, `tagIds[0]`, ...) and deliberately does not echo the offending value.
- `../tests/test_ids.py`: unit tests for `parse_uuid` (canonical, uppercase and hyphen-less forms accepted; short, long, non-hex, empty, `None` and non-string values rejected; message contents).
- `../tests/test_invalid_ids.py`: one end-to-end test per client-supplied ID — `recipe(id)`, `createRecipe` (`categoryId`, `ingredients[].ingredientId`, `tagIds`), `updateRecipe` (`id`, `categoryId`, `ingredients[].ingredientId`, `tagIds`), `deleteRecipe(id)`, `rateRecipe(recipeId)` — plus: nothing is written to the database, no Sentry report, the raw value is not echoed back, and well-formed but unknown IDs behave as before (`Recipe not found`, `deleteRecipe` → `false`).

### Changed
- `recipes.py` parses client-supplied IDs through `parse_uuid`. The `uuid.UUID(self.id)` calls on `Recipe` fields stay as they are: they parse IDs the server generated itself.
- `updateRecipe` with an explicit `categoryId: null` now returns the "Invalid ID" message instead of an "Internal server error".

---

## [0.2.6] - 2026-10-14

### Fixed
- **`ErrorLoggingExtension` was never attached to the schema**, so exception masking was inactive: unexpected database or runtime exceptions reached clients with raw messages (SQL, parameters, internals) and were never sent to Sentry. `app/schema.py` now initializes `strawberry.Schema` with `extensions=[ErrorLoggingExtension]`.

### Added
- `app/errors.py`: Introduced `PublicError`, the base class for domain and business logic exceptions intended for the GraphQL client. Adding a new client-facing exception requires only subclassing `PublicError`.
- `tests/test_error_handling.py`: Comprehensive test suite verifying that public errors pass through unmasked and bypass Sentry, unexpected errors are masked as "Internal server error" and reported to Sentry, syntax/validation errors pass through, sibling query fields remain unaffected, and the extension is properly attached to the production schema.

### Changed
- `app/error_handling.py` now determines exception safety using `isinstance(original, PublicError)` instead of a hard-coded name list.
- GraphQL-level errors (syntax errors, missing variables, unknown fields) pass through unmasked with their original message and are not sent to Sentry.
- Exception logging levels differentiated: `PublicError` and syntax/validation errors are logged as `WARNING`, while unexpected system errors are logged as `ERROR`.
- Domain exceptions (`UsernameOrEmailTakenError`, `InvalidCredentialsError`, `InvalidRefreshTokenError`, `RecipeNotFoundError`, `NotRecipeOwnerError`, `InvalidRatingValueError`, `NotAuthenticatedError`) updated to inherit from `PublicError`.

---

## [0.2.5] - 2026-10-08

### Fixed
- **`pytest` inside the `api` container collected 0 tests.** The container only had the contents of `app/` (volume `./app:/app`), so neither `tests/` nor `pytest.ini` were visible to it — the README command could not work, and pytest-asyncio warned about the unset `asyncio_default_fixture_loop_scope` because `pytest.ini` was never read.
- **Most DB tests failed with "attached to a different loop" / "another operation is in progress".** Async fixtures ran on the session event loop (`asyncio_default_fixture_loop_scope = session`) while each test ran on its own function-scoped loop, so pooled asyncpg connections created by a fixture were reused on another loop. `tests/conftest.py` now marks every async test with `loop_scope="session"` (`pytest_collection_modifyitems`, `append=False` so it wins over the marker auto mode adds).

### Changed
- `docker-compose.yml`: `api` mounts `./tests` → `/tests` and `./pytest.ini` → `/pytest.ini` (read-only). They are deliberately **not** mounted under `/app`: a bind mount nested inside the `./app` bind mount makes Docker create empty stub files/dirs (`app/pytest.ini`, `app/tests/`) on the host.
- `pytest.ini`: `pythonpath = app tests` — relative to the file, so it works from the repo root and in the container (where `/app`, `/tests`, `/pytest.ini` mirror the repo layout). `tests` is required for `from conftest import ...`.
- `README.md`: tests must run inside the container with `-w /`; explains the `KeyError: 'POSTGRES_USER'` seen when running `pytest` on the host, and that the container must be recreated after changing the compose file.

---

## [0.2.4] - 2026-10-05

### Removed
- **Duplicate DB engine in `app/main.py`:** `app/main.py` read `DATABASE_URL` straight from the environment and created its own SQLAlchemy engine, duplicating `app/db.py` (the single source of truth, built from `POSTGRES_*`). `docker-compose.yml` never passed `DATABASE_URL` to the `api` service, so the app depended on an undocumented variable.
- **Dead `Query` type in `app/main.py`:** an unused copy of `hello`/`health`; the real ones live in `app/schema.py`.

### Added
- `tests/test_main.py`: smoke tests for `/`, `hello` and `health`.

---

## [0.2.3] - 2026-10-04

### Added
- **Per-request DataLoaders (`app/loaders.py`, closes #43):**
  - One `strawberry.dataloader.DataLoader` per relation: `user` (recipe author and rating author), `recipe_category`, `ingredient`, `ingredient_category` (many-to-one) and `ingredients_by_recipe`, `tags_by_recipe`, `ratings_by_recipe` (one-to-many).
  - Loaders are created fresh for every request in `get_context` (`info.context["loaders"]`), so the cache never outlives a request.
  - Batch functions return exactly one result per key in key order; one-to-many loaders return `[]` for keys with no rows, many-to-one loaders return a `LookupError` for a missing row.
  - `tests/test_dataloaders.py`: query-count test (constant number of SELECTs for 4 vs 16 recipes), nested-data correctness incl. empty collections, loader contract (key order, empty lists, unknown keys), loaders-are-per-request.

### Changed
- All nested resolvers (`Recipe.author/category/ingredients/tags/ratings/avgRating/ratingsCount`, `Ingredient.category`, `RecipeIngredient.ingredient`, `Rating.user`) now use the loaders instead of opening their own session per field. `avgRating`/`ratingsCount` reuse the `ratings` batch (no extra query).
- Ingredient lines are still ordered by `position`; tags are now ordered by name and ratings by creation time (previously unspecified order).

---

## [0.2.2] - 2026-10-03

### Added
- **Recipe Rating GraphQL Mutation (`rate_recipe` in `app/recipes.py` / `app/schema.py`):**
  - Added `rateRecipe` GraphQL mutation with `RateRecipeInput` allowing authenticated users to rate recipes and leave optional comments.
  - Implemented rating upsert logic based on `UNIQUE(recipe_id, user_id)` constraint — re-rating a recipe updates the existing row rather than inserting a duplicate record.
  - Added optional `comment_text` handling backed by `UNIQUE(rating_id)` constraint — omitting the field leaves existing comments untouched, while providing text creates or replaces the comment independently of the rating value.

### Fixed
- **Database Exception Translation:**
  - Added `InvalidRatingValueError` translating PostgreSQL `CHECK` constraint violations for rating values (must be between 1 and 5) into clean GraphQL error messages.
  - Handled missing targets via `RecipeNotFoundError` when trying to rate non-existent recipe IDs.

---

## [0.2.1] - 2026-10-01

### Added
- **Recipe Management GraphQL Mutations (`app/recipes.py` / `app/schema.py`):**
  - Added `createRecipe`, `updateRecipe`, and `deleteRecipe` mutations wired into GraphQL `Mutation`.
  - Added input structures: `CreateRecipeInput`, `UpdateRecipeInput`, and `RecipeIngredientInput`.
  - Implemented `strawberry.UNSET` sentinel values for `UpdateRecipeInput` fields to distinguish omitted fields ("leave unchanged") from explicitly `null` values (such as clearing the optional `description` field).
  - Added full list replacement strategy for nested `ingredients` and `tag_ids` during update operations (replacing all entries rather than merging).

### Security
- **Author Ownership Check:** Added `NotRecipeOwnerError` exception ensuring only the recipe's original author can perform update or delete operations.
- **Idempotent Deletion:** Implemented `deleteRecipe` as an idempotent mutation returning `false` for non-existent or previously deleted IDs without throwing runtime errors.

---

## [0.2.0] - 2026-09-28

### Added
- **Recipe & Dictionary GraphQL Read Schema (`app/recipes.py` / `app/schema.py`):**
  - Added new dedicated domain module `app/recipes.py` containing Strawberry GraphQL types: `Recipe`, `RecipeCategory`, `IngredientCategory`, `Ingredient`, `RecipeIngredient`, `Tag`, `Rating`, `RatingComment`, `RecipeAuthor`, alongside `Difficulty` and `MeasurementUnit` enums.
  - Added read queries to GraphQL `Query`:
    - `recipe(id: ID!)`: Fetch a single recipe by unique identifier (raises `RecipeNotFoundError` if missing).
    - `myRecipes`: Fetch all recipes created by the currently authenticated user (protected via `require_user`).
    - `recipeCategories`: Dictionary query returning all available recipe categories.
    - `ingredientCategories`: Dictionary query returning all ingredient categories.
    - `ingredients(search: String)`: Master list ingredient lookup with optional case-insensitive substring search (`ILIKE`).

---

## [0.1.8] - 2026-09-21

### Added
- **Automated Test Suite for Foundation & Auth (`tests/`):**
  - Added unit tests (`tests/test_auth_unit.py`) verifying Argon2id password hashing and verification, short-lived JWT access token generation & payload decoding, and SHA-256 refresh token hashing.
  - Added integration tests (`tests/test_auth_graphql.py`) for GraphQL HTTP endpoints (`register`, `login`, `refreshToken`, `logout`, `currentUser`) testing both happy paths and error paths.
  - Added idempotency tests (`tests/test_seed.py`) confirming `app/seed.py` can be re-run safely (`INSERT ... ON CONFLICT DO NOTHING`) without creating duplicate records.

---

## [0.1.7] - 2026-09-20

### Added
- **Automated Test Suite (`tests/`):**
  - Added unit and regression tests for DSN URL-encoding logic in `app/db.py` (handling passwords with special characters like `@`, `:`, `/`, `#`).
  - Added schema constraint validation tests: unique constraints (`User.username`, `User.email`, `RecipeCategory.name`, `IngredientCategory.name`, `IngredientCatalog.name`, `Tag.name`), composite rating constraint (one rating per user per recipe), 1:1 constraint for rating comments, and check constraint for rating values (`1-5`).
  - Added ENUM persistence verification confirming PostgreSQL stores lowercase values matching `values_callable` mapping.
  - Test suite configured to execute against disposable database (`recipes_test_db`) with automatic table truncation (`TRUNCATE`) between test runs.
  - Configured `pythonpath = app` in `pytest.ini` for clean module resolution across application imports.

### Refactored
- **Project Structure Reorganization:** Restructured project layout by moving `tests/` from `app/` to the repository root.

---

## [0.1.6] - 2026-09-14

### Added
- **Structured JSON Logging (`app/logging_config.py`):** Integrated `structlog` configured for JSON output across the application.
- **GraphQL Exception Handling Extension (`app/schema.py` / `ErrorLoggingExtension`):**
  - Added Strawberry `ErrorLoggingExtension` to log every resolver exception with full tracebacks.
  - Implemented exception masking logic.
- **Exception Tracking with Sentry (`app/sentry_config.py`):**
  - Added Sentry integration reading from `SENTRY_DSN` (silently disabled when unset).
  - Added `SENTRY_DSN` to `.env.example` and `docker-compose.yml`.

---

## [0.1.5] - 2026-09-13

### Added
- **Per-Request Auth Context (`app/context.py`):**
  - Added Strawberry `get_context` getter to extract `Authorization: Bearer <token>`, verify JWT, and populate user context via `info.context["user"]`.
  - Graceful degradation for unauthenticated or malformed/expired token requests (`user = None`).
  - Reusable `require_user(info)` helper raising `NotAuthenticatedError` for protected GraphQL resolvers.
  - Added `currentUser` GraphQL query returning authenticated user profile or `null`.

---

## [0.1.4] - 2026-09-12

### Added
- **GraphQL Session Management Mutations (`app/schema.py`):**
  - Added `refreshToken` mutation: validates refresh tokens by SHA-256 hash (checking existence, expiration, and revocation status) and returns a new access token.
  - Added `logout` mutation: revokes refresh tokens by setting `revoked_at`.
  - Unified generic error messaging across refresh failures.

### Refactored
- Extracted `hash_refresh_token` helper function from `create_refresh_token` in `app/auth.py` to ensure consistent SHA-256 hashing logic.

---

## [0.1.3] - 2026-09-11

### Added
- **Authentication System (`app/auth.py`):**
  - Password hashing via `argon2id` using `passlib`.
  - Short-lived JWT access tokens (15 min lifespan) with stateless verification.
  - Opaque random refresh tokens (`secrets.token_urlsafe`), persisted in `refresh_tokens` table via SHA-256 hashes.
- **GraphQL Schema (`app/schema.py`):**
  - Moved GraphQL schema into `app/schema.py`.
  - Added `register` and `login` GraphQL mutations.
  - Added `AuthPayload` and `User` GraphQL types.

---

## [0.1.2] - 2026-09-09

### Added
- Reference data seeding script (`app/seed.py`) with 42 recipe categories, 15 ingredient categories, and 260+ base ingredients.
- Idempotent insert mechanism using PostgreSQL `INSERT ... ON CONFLICT DO NOTHING`.

---

## [0.1.1] - 2026-09-08

### Added
- SQLAlchemy models for the full data schema (12 tables) — `app/models.py`.
- Initial Alembic migration and timezone-aware migration (`TIMESTAMPTZ`).
- `app/db.py` — shared async engine/session factory.

### Fixed
- URL-encoding logic in `app/db.py` for database passwords containing reserved characters.
- Docker context and project structure cleanups.

---

## [0.1.0] - 2026-09-03

### Added
- Project infrastructure: `docker-compose.yml` (Postgres, Kafka, Elasticsearch, monitoring).
- FastAPI + Strawberry API boilerplate with live-reload.
- 