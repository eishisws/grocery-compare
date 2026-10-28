# grocery-compare

Type a shopping list, see real totals at stores near you.

## Architecture

Two **independent prongs**. They never call each other — the database is the
single source of truth and their only shared interface.

```
 client ──> frontend/ ──> api/  ─────────┐
                                         ├──>  Postgres (PostGIS + pgvector)
 GitHub Actions cron ──> price-getter/ ──┘
```

| Folder | Role | Stack |
|---|---|---|
| `api/` | Client-facing service: geocode location → nearby stores → basket totals. Stateless read/compute only. | FastAPI, SQLAlchemy, PostGIS |
| `price-getter/` | Batch worker (nightly/bi-nightly cron): scrape stores, parse lists with an LLM, normalize unit prices, write prices + embeddings. | httpx, Playwright, sentence-transformers, LLM API |
| `database/` | Schema of record: Alembic migrations + reference DDL. | Postgres, PostGIS, pgvector |
| `frontend/` | List input, results, store detail (mobile-first). | Next.js, TypeScript, Tailwind, shadcn/ui, TanStack Query, MapLibre |
| `.github/workflows/` | `price-getter.yml` (cron), `ci.yml` (lint + test + build). | GitHub Actions |

## Run locally

Each Python prong is its own `uv` project — install, run, test separately:

```bash
# 1. Database (needs Postgres with PostGIS + pgvector — Supabase/Neon ship both)
cd database && uv sync && uv run alembic upgrade head

# 2. API  (http://localhost:8000, docs at /docs)
cd api && uv sync && uv run uvicorn app.main:app --reload
cd api && uv run pytest

# 3. Price getter (batch run, no server; needs DATABASE_URL + LLM key in .env)
cd price-getter && uv sync && uv run price-getter

# 4. Frontend (http://localhost:3000)
cd frontend && npm install && npm run dev
```

Notes:

- Point both prongs at the same database via `DATABASE_URL` (`.env` supported).
- Embedding model is an optional extra: `uv sync --extra matching` in
  'price-getter' pulls sentence-transformers (torch).
- Playwright browsers: `uv run playwright install chromium` in `price-getter`.
- Deploy targets: `frontend` → Vercel, `api` → Render/Railway/Fly, Postgres →
  Supabase/Neon.

## Golden rule

Business logic reads and writes prices/stores **only through Postgres**. If a
prong needs a fact, it queries the database; nothing is hardcoded, and no
service-to-service HTTP exists.
