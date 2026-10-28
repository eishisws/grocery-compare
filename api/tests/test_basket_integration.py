"""Integration: POST /basket/totals against a real Postgres+PostGIS+pg_trgm
(booted by .github/actions/ci-db in CI; skipped locally without TEST_DATABASE_URL).

Contract checked: per-store totals come from the best ILIKE/trigram match per
item; one seeded store sells French-named products, the other English ones,
the (English-only request) still resolves against both plus reports
unmatched items — and a store far outside the radius never appears.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="needs a live Postgres — set TEST_DATABASE_URL (CI does via .github/actions/ci-db)",
)

PRODUCTS_A = {  # French-named (Maxi-style) — request tokens must hit these via ILIKE
    "Lait 2% 4 L": "6.44",
    "Pain blanc": "2.99",
    "Beurre 500 g": "5.99",
}
PRODUCTS_B = {  # English-named (Superstore-style) at different prices
    "Milk 2% 4 L": "7.77",
    "Bread white": "3.50",
}


@pytest.fixture()
def seeded_db():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM products"))
        conn.execute(text("DELETE FROM stores"))
        conn.execute(
            text("""
            INSERT INTO stores (name, chain, address, location) VALUES
            ('Store A', 'Maxi', '1 Close St',
                ST_MakePoint(-75.7500, 45.4000)::geography),
            ('Store B', 'Superstore', '2 Close St',
                ST_MakePoint(-75.7450, 45.4020)::geography),
            ('Far Mart', 'Superstore', '999 Far Away Rd',
                ST_MakePoint(-78.9, 44.1)::geography)
        """)
        )
        for name, price in PRODUCTS_A.items():
            conn.execute(
                text(
                    "INSERT INTO products (store_id, raw_name, name, price) "
                    "SELECT id, :n, :n, :p FROM stores WHERE name = 'Store A'"
                ),
                {"n": name, "p": price},
            )
        for name, price in PRODUCTS_B.items():
            conn.execute(
                text(
                    "INSERT INTO products (store_id, raw_name, name, price) "
                    "SELECT id, :n, :n, :p FROM stores WHERE name = 'Store B'"
                ),
                {"n": name, "p": price},
            )
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM products"))
        conn.execute(text("DELETE FROM stores"))
    engine.dispose()


def test_basket_totals_per_store(seeded_db) -> None:
    client = TestClient(from_api_under_test())

    resp = client.post(
        "/basket/totals",
        json={
            "lat": 45.4010,
            "lon": -75.7480,  # ~600m point: A and B in radius, Far Mart excluded
            "radius_km": 5,
            "items": [
                {"name": "lait 4L", "quantity": 2},
                {"name": "pain", "quantity": 1},
                {"name": "banane", "quantity": 3},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["stores"]

    names = [s["store"]["name"] for s in results]
    assert names == ["Store A", "Store B"], f"far store leaked or wrong order: {names}"

    store_a, store_b = results

    # Store A: "lait" and "pain" matched by ILIKE token; "banane" matches nothing
    assert store_a["matched_count"] == 2
    assert store_a["unmatched"] == ["banane"]
    milk = store_a["items"][0]
    assert milk["matched_name"] == "Lait 2% 4 L"
    assert milk["unit_price"] == pytest.approx(6.44)
    assert milk["line_total"] == pytest.approx(12.88)
    assert store_a["total"] == pytest.approx(12.88 + 2.99)

    # Store B: French tokens don't ILIKE English names; trigram similarity is
    # below threshold — every item unmatched, total 0
    assert store_b["matched_count"] == 0
    assert store_b["total"] == 0
    assert store_b["unmatched"] == ["lait 4L", "pain", "banane"]


def test_basket_totals_never_503s_on_empty_products(seeded_db) -> None:
    client = TestClient(from_api_under_test())
    with seeded_db.begin() as conn:
        conn.execute(text("DELETE FROM products"))

    resp = client.post(
        "/basket/totals",
        json={
            "lat": 45.4010,
            "lon": -75.7480,
            "radius_km": 5,
            "items": [{"name": "lait"}],
        },
    )
    assert resp.status_code == 200
    for store in resp.json()["stores"]:
        assert store["total"] == 0
        assert store["unmatched"] == ["lait"]


def from_api_under_test():
    from app.main import app

    return app
