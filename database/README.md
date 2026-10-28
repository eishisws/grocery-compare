# database — source of truth

Nothing here is client-facing. Alembic owns the schema; `schema.sql` is the
reference DDL to eyeball (needs Postgres with PostGIS, pgvector, pg_trgm —
Supabase and Neon ship all three).

The two prongs (`api/`, `price-getter/`) read/write Postgres and nothing else.
They share no code and never talk to each other.

## Bootstrap

```bash
uv sync
# once, against your Postgres:
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/grocery
uv run alembic upgrade head
```

## Making schema changes

Write a revision by hand or autogenerate one, review it, then:

```bash
uv run alembic revision -m "add table X"
uv run alembic upgrade head   # apply locally, then commit the migration
```

API and price-getter just point `DATABASE_URL` at the same database —
migrations are applied here, nowhere else.
