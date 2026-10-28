"""Pipeline entry point. Runs on a GitHub Actions cron (nightly by default).

Steps, in order:
1. scrape     -> raw product records per store      (scraping.py, per-source)
2. normalize  -> names + unit-price math             (units.py)
3. match      -> embeddings + LLM verdicts           (matching.py)
4. persist    -> idempotent upserts into Postgres    (persist.py)

Nothing here talks to the API prong: Postgres is the only shared interface.
"""

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

log = logging.getLogger("price-getter")


def run() -> None:
    # TODO: add sources to scraping.py per store, then wire:
    #   records = scrape(sources)
    #   normalized = [normalize(r) for r in records]           # uses units.price_per_100g/l
    #   settled   = embed_and_match(normalized)                # uses matching
    #   persist(settled, engine)                               # upsert into products/stores
    log.info("price-getter pipeline placeholder run — no sources configured yet")


if __name__ == "__main__":
    run()
