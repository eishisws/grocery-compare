"""Integration: the write side against a real Postgres+pgvector (booted by
.github/actions/ci-db in CI; skipped locally when TEST_DATABASE_URL is unset).

Contract checked: upserts are idempotent — nightly reruns must update rows in
place (the source of truth never accumulates duplicates or drifts).
"""

import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from price_getter import persist

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="needs a live Postgres — set TEST_DATABASE_URL (CI does via .github/actions/ci-db)",
)

STORE_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture()
def db():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM stores"))  # cascades to products
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM stores"))
    engine.dispose()


def test_store_upsert_is_idempotent_by_id(db) -> None:
    sid = persist.persist_store(
        name="Test Mart", chain="TestCo", lat=43.6591, lon=-79.3789, store_id=STORE_ID
    )
    persist.persist_store(
        name="Test Mart Renamed", chain="TestCo", lat=43.6591, lon=-79.3789, store_id=STORE_ID
    )
    assert sid == STORE_ID

    with db.connect() as conn:
        count, name = conn.execute(
            text("SELECT count(*), max(name)::text FROM stores WHERE id = :sid"),
            {"sid": STORE_ID},
        ).one()
    assert count == 1, "re-persisting a store must update, not duplicate"
    assert name == "Test Mart Renamed"


def test_product_repersist_updates_not_duplicates(db) -> None:
    persist.persist_store(name="Test Mart", lat=43.6591, lon=-79.3789, store_id=STORE_ID)

    persist.persist_product(
        store_id=STORE_ID,
        raw_name="HOME MILK 2% 2L",
        name="2% Milk 2L",
        price="5.49",
        quantity="2",
        quantity_unit="l",
        price_per_l="2.7450",
    )
    persist.persist_product(
        store_id=STORE_ID,
        raw_name="HOME MILK 2% 2L (decoded 2026-10-28)",
        name="2% Milk 2L",  # same display name -> same (store_id, name) key
        price="5.99",
        quantity="2",
        quantity_unit="l",
        price_per_l="2.9950",
    )

    with db.connect() as conn:
        count, price, per_l = conn.execute(
            text("""
                SELECT count(*), max(price), max(price_per_l)
                FROM products WHERE store_id = :sid AND name = :name
            """),
            {"sid": STORE_ID, "name": "2% Milk 2L"},
        ).one()
    assert count == 1, "same product must update in place, never duplicate"
    assert Decimal(price) == Decimal("5.99")
    assert Decimal(per_l) == Decimal("2.9950")


def test_embedding_roundtrip_via_vector_cast(db) -> None:
    persist.persist_store(name="Test Mart", lat=43.6591, lon=-79.3789, store_id=STORE_ID)
    embed = [0.1] * 384
    persist.persist_product(
        store_id=STORE_ID,
        raw_name="BUTTER 500 G",
        name="Butter 500g",
        price="7.25",
        quantity="500",
        quantity_unit="g",
        price_per_100g="1.45",
        embedding=embed,
    )
    with db.connect() as conn:
        stored = conn.execute(
            text("SELECT embedding::text FROM products WHERE store_id = :sid"),
            {"sid": STORE_ID},
        ).scalar()
    assert stored is not None
    values = [float(v) for v in stored.strip("[]").split(",")]
    assert len(values) == 384
    assert all(v == pytest.approx(0.1) for v in values)
