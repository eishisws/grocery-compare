"""initial source-of-truth schema: stores + products (PostGIS, pgvector, pg_trgm)

Hand-written to mirror database/schema.sql. Do NOT autogenerate migrations that
diverge from schema.sql — CI diffs alembic head against it (schema parity gate)
and fails the branch on drift.

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS postgis",
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    # --- stores -------------------------------------------------------------
    (
        "CREATE TABLE IF NOT EXISTS stores (\n"
        "    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
        "    name        TEXT NOT NULL,\n"
        "    chain       TEXT,\n"
        "    address     TEXT,\n"
        "    location    GEOGRAPHY(Point, 4326) NOT NULL,\n"
        "    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()\n"
        ")"
    ),
    "CREATE INDEX IF NOT EXISTS stores_location_gix ON stores USING GIST (location)",
    # --- products -----------------------------------------------------------
    (
        "CREATE TABLE IF NOT EXISTS products (\n"
        "    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n"
        "    store_id        UUID NOT NULL REFERENCES stores (id) ON DELETE CASCADE,\n"
        "    raw_name        TEXT NOT NULL,\n"
        "    name            TEXT NOT NULL,\n"
        "    price           NUMERIC(10, 2) NOT NULL,\n"
        "    currency        TEXT NOT NULL DEFAULT 'CAD',\n"
        "    quantity        NUMERIC(12, 4),\n"
        "    quantity_unit   TEXT,\n"
        "    price_per_100g  NUMERIC(10, 4),\n"
        "    price_per_l     NUMERIC(10, 4),\n"
        "    embedding       VECTOR(384),\n"
        "    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),\n"
        "    UNIQUE (store_id, name)\n"
        ")"
    ),
    "CREATE INDEX IF NOT EXISTS products_store_gix ON products (store_id)",
    "CREATE INDEX IF NOT EXISTS products_name_gix ON products USING GIN (name gin_trgm_ops)",
]


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS products CASCADE")
    op.execute("DROP TABLE IF EXISTS stores CASCADE")
