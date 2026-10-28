"""Write side of the source of truth.

The price-getter owns these upserts (stores, products) and nothing else writes
to the database — the API and nightly cron both keep that contract. Upserts
are idempotent so nightly and bi-nightly runs converge instead of duplicating.
"""

import uuid
from decimal import Decimal

from sqlalchemy import text

from price_getter.db import get_engine

_UPSERT_STORE = text("""
    INSERT INTO stores (id, name, chain, address, location)
    VALUES (:id, :name, :chain, :address, ST_MakePoint(:lon, :lat)::geography)
    ON CONFLICT (id) DO UPDATE SET
        name     = EXCLUDED.name,
        chain    = EXCLUDED.chain,
        address  = EXCLUDED.address,
        location = EXCLUDED.location
    RETURNING id
""")

_UPSERT_PRODUCT = text("""
    INSERT INTO products (
        id, store_id, raw_name, name, price, currency,
        quantity, quantity_unit, price_per_100g, price_per_l, embedding, updated_at
    )
    VALUES (
        :id, :store_id, :raw_name, :name, :price, :currency,
        :quantity, :quantity_unit, :price_per_100g, :price_per_l,
        CAST(:embedding AS vector),
        now()
    )
    ON CONFLICT (store_id, name) DO UPDATE SET
        price          = EXCLUDED.price,
        currency       = EXCLUDED.currency,
        quantity       = EXCLUDED.quantity,
        quantity_unit  = EXCLUDED.quantity_unit,
        price_per_100g = EXCLUDED.price_per_100g,
        price_per_l    = EXCLUDED.price_per_l,
        embedding      = EXCLUDED.embedding,
        updated_at     = now()
    RETURNING id
""")


def persist_store(
    *,
    name: str,
    chain: str | None = None,
    address: str | None = None,
    lat: float,
    lon: float,
    store_id: str | None = None,
) -> str:
    """Upsert one store (idempotent by `store_id`) and return its stable id."""
    sid = store_id or str(uuid.uuid4())
    with get_engine().begin() as conn:
        result = conn.execute(
            _UPSERT_STORE,
            {
                "id": sid,
                "name": name,
                "chain": chain,
                "address": address,
                "lat": lat,
                "lon": lon,
            },
        )
        row = result.scalar_one()
    return str(row)


def persist_product(
    *,
    store_id: str,
    raw_name: str,
    name: str,
    price: Decimal | float | str,
    currency: str = "CAD",
    quantity: Decimal | float | str | None = None,
    quantity_unit: str | None = None,
    price_per_100g: Decimal | float | str | None = None,
    price_per_l: Decimal | float | str | None = None,
    embedding: list[float] | None = None,
) -> str:
    """Upsert one product under its store (conflict key: store_id + name).
    Re-persisting the same product with new values updates in place.
    """
    embedding_text = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]" if embedding else None
    pid = str(uuid.uuid4())
    with get_engine().begin() as conn:
        row = conn.execute(
            _UPSERT_PRODUCT,
            {
                "id": pid,
                "store_id": store_id,
                "raw_name": raw_name,
                "name": name,
                "price": str(price),
                "currency": currency,
                "quantity": None if quantity is None else str(quantity),
                "quantity_unit": quantity_unit,
                "price_per_100g": None if price_per_100g is None else str(price_per_100g),
                "price_per_l": None if price_per_l is None else str(price_per_l),
                "embedding": embedding_text,
            },
        ).scalar_one()
    return str(row)
