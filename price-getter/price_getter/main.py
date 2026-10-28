"""Pipeline entry point. Runs on a GitHub Actions cron (nightly by default).

Steps, in order:
1. scrape     -> raw product records per store      (sources/*)
2. normalize  -> names + unit-price math             (units.py, planned)
3. match      -> embeddings + LLM verdicts           (matching.py, planned)
4. persist    -> idempotent upserts into Postgres    (persist.py)

Today the pipeline persists products with plain names + prices; quantity /
unit-price extraction from descriptions is the LLM-pass milestone. Nothing
here talks to the API prong: Postgres is the only shared interface.

The database is the source of truth for store identity too: the pipeline
resolves the seeded Maxi row by chain + name instead of hard-coding ids.
"""

import logging
import sys

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

log = logging.getLogger("price-getter")

# French search terms — the Maxi site (Quebec) serves French results, which
# the frontend later matches against user baskets regardless of language.
DEFAULT_MAXI_QUERIES: tuple[str, ...] = (
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

MAXI_CHAIN = "Maxi"
MAXI_NAME_LIKE = "%hull%"  # "Maxi Hull" in the seeded stores row


def _resolve_store_id(engine, *, chain: str, name_like: str) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM stores WHERE chain = :chain AND name ILIKE :name"),
            {"chain": chain, "name": name_like},
        ).first()
    return str(row[0]) if row else None


def run() -> None:
    from price_getter.db import get_engine
    from price_getter.persist import persist_product
    from price_getter.sources import maxi

    engine = get_engine()
    store_id = _resolve_store_id(engine, chain=MAXI_CHAIN, name_like=MAXI_NAME_LIKE)
    if store_id is None:
        raise SystemExit(f"no store row matching chain={MAXI_CHAIN!r} name~{MAXI_NAME_LIKE!r}")

    persisted = blocked = 0
    with maxi.maxi_search() as fetch_search:
        for query in DEFAULT_MAXI_QUERIES:
            try:
                records = fetch_search(query)
            except maxi.MaxiBlockedError as exc:
                log.warning("Akamai blocked %r: %s", query, exc)
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
            log.info("maxi %r: %d products (total persisted=%d)", query, len(records), persisted)

    log.info(
        "done: %d persist upserts, %d/%d queries Akamai-blocked (store_id=%s)",
        persisted,
        blocked,
        len(DEFAULT_MAXI_QUERIES),
        store_id,
    )
    if persisted == 0:
        raise SystemExit("no products persisted — check block warnings above")


if __name__ == "__main__":
    sys.exit(run())
