"""Add one real store to the source of truth: Nominatim geocode -> persist_store.

Dry run by default (prints everything, writes nothing):

    DATABASE_URL=... uv run python scripts/add_store.py \
        --query "Walmart Supercentre, 1375 Baseline Rd, Ottawa, ON" --chain Walmart

Write it for real by adding --commit:

    DATABASE_URL=... uv run python scripts/add_store.py ... --commit

Store ids are derived (uuid5) from --name, so re-running with the same name
UPDATEs the row (the idempotent-write contract CI checks) instead of
duplicating. Duplicates poison distance/basket logic — never hand-roll ids.
"""

import argparse
import sys
import uuid

import httpx

from price_getter.persist import persist_store

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "grocery-compare/0.1 (store seeding)"
_STORE_NS = uuid.UUID("a8e2c3c1-d0a7-42e0-b2f0-000000000001")


def geocode(query: str) -> tuple[float, float, str]:
    resp = httpx.get(
        NOMINATIM_SEARCH,
        params={"q": query, "format": "jsonv2", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=15.0,
    )
    resp.raise_for_status()
    hits = resp.json()
    if not hits:
        sys.exit(f"no geocode match for {query!r} — refine the query")
    hit = hits[0]
    return float(hit["lat"]), float(hit["lon"]), str(hit["display_name"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        required=True,
        help="free-text search, e.g. 'Maxi, 1 Boulevard du Plateau, Gatineau, QC'",
    )
    parser.add_argument("--name", help="display name in the DB (default: the query itself)")
    parser.add_argument("--chain", help="banner, e.g. Walmart / Maxi / Metro / Loblaws")
    parser.add_argument("--address", help="overrides the geocoder's label as the address")
    parser.add_argument("--commit", action="store_true", help="write to the database")
    args = parser.parse_args()

    lat, lon, label = geocode(args.query)
    name = args.name or args.query
    address = args.address or label
    store_id = str(uuid.uuid5(_STORE_NS, name))

    print(f"query    : {args.query}")
    print(f"geocoded : {label}")
    print(f"coords   : {lat:.6f}, {lon:.6f}")
    print(f"name     : {name}")
    print(f"chain    : {args.chain or '(none)'}")
    print(f"store id : {store_id}")

    if not args.commit:
        print("\n(dry run — add --commit to persist this store)")
        return

    sid = persist_store(
        name=name, chain=args.chain, address=address, lat=lat, lon=lon, store_id=store_id
    )
    print(f"persisted store {sid} ✓")


if __name__ == "__main__":
    main()
