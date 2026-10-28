"""Pipeline entry point. Runs on a GitHub Actions cron (nightly by default).

Steps, in order:
1. scrape     -> raw product records per store      (sources/*)
2. normalize  -> names + unit-price math             (units.py, planned)
3. match      -> embeddings + LLM verdicts           (matching.py, planned)
4. persist    -> idempotent upserts into Postgres    (persist.py)

Today the pipeline persists products with plain names + prices; quantity /
unit-price extraction from descriptions is the LLM-pass milestone. Nothing
here talks to the API prong: Postgres is the only shared interface.

The database is the source of truth for store identity too: each banner run
resolves its seeded store row by chain + name instead of hard-coding ids.
Banner failures are isolated: a blocked banner never blocks the others; the
whole run exits non-zero only when NOTHING could be scraped at all.
"""

import logging
import sys
from dataclasses import dataclass

from sqlalchemy import text

from price_getter.sources.pcx import MAXI, SUPERSTORE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

log = logging.getLogger("price-getter")


@dataclass(frozen=True)
class BannerRun:
    """One PCX banner: where to scrape, whose store row to write under."""

    banner: object  # sources.pcx.PCXBanner
    store_chain: str  # `stores.chain` value in the DB
    store_name_like: str  # ILIKE fragment identifying the one store row
    queries: tuple[str, ...]


MAXI_QUERIES: tuple[str, ...] = (
    "lait",
    "pain",
    "beurre",
    "oeufs",
    "yaourt",
    "fromage",
    "pates",
    "riz",
    "poulet",
    "boeuf hache",
    "cafe",
    "pommes",
    "bananes",
    "céréales",
    "savon",
)

SUPERSTORE_QUERIES: tuple[str, ...] = (
    "milk",
    "bread",
    "butter",
    "eggs",
    "yogurt",
    "cheese",
    "pasta",
    "rice",
    "chicken",
    "ground beef",
    "coffee",
    "apples",
    "bananas",
    "cereal",
    "soap",
)

# Two prongs of evidence per banner: the PCX storeId (informational; the BFF
# uses Loblaws' legacy numbering) maps to a seeded uuid row via chain+name.
RUNS: tuple[BannerRun, ...] = (
    BannerRun(
        banner=MAXI,
        store_chain="Maxi",
        store_name_like="%hull%",
        queries=MAXI_QUERIES,
    ),
    BannerRun(
        banner=SUPERSTORE,
        store_chain="Superstore",
        store_name_like="%richmond%",
        queries=SUPERSTORE_QUERIES,
    ),
)


def _resolve_store_id(engine, *, chain: str, name_like: str) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM stores WHERE chain = :chain AND name ILIKE :name"),
            {"chain": chain, "name": name_like},
        ).first()
    return str(row[0]) if row else None


def _scrape_banner(run: BannerRun, store_id: str | None) -> int:
    """Scrape one banner into DB rows; return the number persisted."""
    from price_getter.persist import persist_product
    from price_getter.sources import pcx

    if store_id is None:
        log.warning(
            "banner %s: no store row for chain=%r name~%r — add it with scripts/add_store.py, skipping",
            run.banner.key,
            run.store_chain,
            run.store_name_like,
        )
        return 0

    persisted = blocked = 0
    with pcx.pcx_search(run.banner) as fetch_search:
        for query in run.queries:
            try:
                records = fetch_search(query)
            except pcx.PCXBlockedError as exc:
                log.warning("pcx[%s] Akamai blocked %r: %s", run.banner.key, query, exc)
                blocked += 1
                continue
            for rec in records:
                persist_product(
                    store_id=store_id,
                    raw_name=rec["name"],
                    name=rec["name"],
                    price=rec["price"],
                    currency=rec["currency"],
                )
                persisted += 1
            log.info(
                "pcx[%s] %r: %d products (banner total=%d)",
                run.banner.key,
                query,
                len(records),
                persisted,
            )

    log.info(
        "pcx[%s] done: %d persist upserts, %d/%d queries blocked (store_id=%s)",
        run.banner.key,
        persisted,
        blocked,
        len(run.queries),
        store_id,
    )
    return persisted


def run() -> None:
    from price_getter.db import get_engine
    from price_getter.sources import pcx

    engine = get_engine()

    total = 0
    for run_cfg in RUNS:
        try:
            store_id = _resolve_store_id(
                engine, chain=run_cfg.store_chain, name_like=run_cfg.store_name_like
            )
            total += _scrape_banner(run_cfg, store_id)
        except pcx.PCXBlockedError as exc:
            log.warning("pcx[%s] banner-level block, skipping run: %s", run_cfg.banner.key, exc)

    log.info("pipeline done: %d persist upserts across %d banners", total, len(RUNS))
    if total == 0:
        raise SystemExit("no products persisted — every banner was blocked or had no store row")


if __name__ == "__main__":
    sys.exit(run())
