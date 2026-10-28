-- Reference DDL for the grocery-compare schema.
-- Alembic migrations in ./alembic/versions are what actually run — keep both in
-- sync (or regenerate revisions from this file when bootstrapping).
-- Needs Postgres with PostGIS + pgvector (Supabase and Neon both ship them).

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- fuzzy/similarity name matching

CREATE TABLE IF NOT EXISTS stores (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    chain       TEXT,
    address     TEXT,
    location    GEOGRAPHY(Point, 4326) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS stores_location_gix ON stores USING GIST (location);

CREATE TABLE IF NOT EXISTS products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores (id) ON DELETE CASCADE,
    raw_name        TEXT NOT NULL,          -- scraped, untouched
    name            TEXT NOT NULL,          -- LLM-cleaned display name
    price           NUMERIC(10, 2) NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'CAD',
    quantity        NUMERIC(12, 4),         -- size on the label
    quantity_unit   TEXT,                   -- g | kg | ml | L | count
    price_per_100g  NUMERIC(10, 4),         -- normalized, fair comparisons
    price_per_l     NUMERIC(10, 4),
    embedding       VECTOR(384),            -- sentence-transformers MiniLM
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (store_id, name)
);

CREATE INDEX IF NOT EXISTS products_store_gix ON products (store_id);
CREATE INDEX IF NOT EXISTS products_name_gix ON products USING GIN (name gin_trgm_ops);
