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
| `.github/workflows/` | `ci.yml` (gates below), `price-getter.yml` (cron), `deploy.yml` (CD). | GitHub Actions |

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

## CI/CD — the contract enforcement layer

Because the prongs are independent, CI is what keeps them independent *and*
keeps both honest against the source of truth. Every push/PR runs:

| Gate | Job | What it proves |
|---|---|---|
| **Isolation** | `isolation` | Neither prong imports the other — Postgres is the only shared interface (`.github/scripts/check_isolation.py`) |
| **Schema parity** | `database` | `alembic upgrade head` on a scratch DB is byte-equivalent in structure (tables/columns/types/defaults/indexes) to `schema.sql`. Drift in either direction fails |
| **Read path** | `api` | `/stores/nearby` against live PostGIS: only in-radius stores, sorted by real distance (seeds via pure SQL, no price-getter involvement) |
| **Write path** | `price-getter` | `persist_*` upserts against live Postgres+pgvector: reruns update in place, never duplicate; embeddings round-trip |
| **Build** | `frontend` | `next build` (all TypeScript errors surface here) |

Every DB job boots the same disposable container (`.github/actions/ci-db`,
built from `database/docker/Dockerfile`: PostGIS + pgvector + pg_trgm) and
applies the real `schema.sql` — no mocks anywhere.

**Making CI binding:** in GitHub → Settings → Branches, add branch protection
for `main` and make these status checks required: `isolation`, `database`,
`api`, `price-getter`, `frontend`. CI/CD then can't be bypassed.

**Nightly (`price-getter.yml`):** the pipeline refuses to run unless
`database/scripts/verify_source_of_truth.py` passes against the production DB —
extensions + tables present. A cron run against a broken database aborts.

**CD (`deploy.yml`):** on push to `main`, gated per-host by repo *variables* so
it stays inert until wired (see its header comment): migrations always outrun
deploys, and the API gets a `/health` smoke test before the run goes green.

## Golden rule

Business logic reads and writes prices/stores **only through Postgres**. If a
prong needs a fact, it queries the database; nothing is hardcoded, and no
service-to-service HTTP exists.
