"""Live smoke test for the Maxi source: fetch one search page, print parsed rows.

No DB writes — this only exercises search/navigation/extraction.
    DATABASE_URL not required. Run: uv run python scripts/smoke_maxi.py [query]
"""

import sys

from price_getter.sources import maxi


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "lait"
    with maxi.maxi_search() as fetch:
        rows = fetch(query)
    print(f"query: {query!r} -> {len(rows)} products")
    for r in rows[:10]:
        print(f"  ${r['price']:>7}  {r['name']}  [{r['brand']}]")
    assert rows, "expected products for a milk search"


if __name__ == "__main__":
    main()
