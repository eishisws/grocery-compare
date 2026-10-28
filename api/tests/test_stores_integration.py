"""Integration: the read side of the source of truth, against a real
Postgres+PostGIS (booted by .github/actions/ci-db in CI; skipped locally when
TEST_DATABASE_URL is not set).

Contract checked: `GET /stores/nearby` returns ONLY stores within `radius_km`,
sorted by PostGIS-computed distance. Seeding is pure SQL — this prong is
tested in isolation from price-getter, exactly as it runs in production.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="needs a live Postgres — set TEST_DATABASE_URL (CI does via .github/actions/ci-db)",
)


@pytest.fixture()
def seeded_db():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM stores"))
        conn.execute(
            text("""
            INSERT INTO stores (name, chain, address, location) VALUES
            ('Corner Market', 'TestCo', '123 Queen St W',
                ST_MakePoint(-79.3832, 43.6532)::geography),
            ('Far Mart', 'TestCo', '999 Far Away Rd',
                ST_MakePoint(-78.9, 44.1)::geography)
        """)
        )
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM stores"))
    engine.dispose()


def test_nearby_filters_by_radius_and_orders_by_distance(seeded_db) -> None:
    # In CI, DATABASE_URL and TEST_DATABASE_URL point at the same database,
    # so the app under test reads the store we seeded via SQL directly.
    # Query from a distinct point (~700 m from 'Corner Market') so the distance
    # math is truly exercised, not a degenerate identical-point query.
    client = TestClient(from_api_under_test())

    resp = client.get("/stores/nearby", params={"lat": 43.6577, "lon": -79.3892, "radius_km": 10})
    assert resp.status_code == 200
    stores = resp.json()

    assert [s["name"] for s in stores] == ["Corner Market"], (
        "expected only the in-radius store: an extra store or wrong ordering crept in"
    )
    distance = stores[0]["distance_km"]
    assert 0 < distance < 1.0, f"query point should be sub-1km from the store, got {distance}"
    assert stores[0]["lat"] == pytest.approx(43.6532, abs=1e-6)
    assert stores[0]["lon"] == pytest.approx(-79.3832, abs=1e-6)


def from_api_under_test():
    from app.main import app

    return app
