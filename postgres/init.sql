-- Executed automatically upon the first startup of the Postgres container.

-- Extension for collecting query statistics (required for monitoring and pgHero).
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- For working with trigram search directly in Postgres — for example, to compare it with Elasticsearch.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- For UUID primary keys
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
