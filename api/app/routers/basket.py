"""Basket totals: per nearby store, sum of the best matching product per item.

Matching strategy (in priority order):
1. Name matching — token ILIKE hits first, then pg_trgm similarity on the
   full item string (this revision): finds `lait 4L` inside `Lait 2% 4 L`.
2. Embedding kNN via pgvector — needs products.embedding populated      (next)
3. LLM settle between close candidates — same dependency

Note: name-based matching is language-sensitive (Maxi sells `Lait`, RCSS
sells `Milk`); the multilingual-embedding pass (step 2) is what makes a
single basket resolve across banners.

The request/response shape is frozen so the frontend can build against it.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_engine
from app.routers.stores import NEARBY_SQL, StoreOut

router = APIRouter(prefix="/basket", tags=["basket"])

# MVP read-side budget: five nearest stores, twenty basket items is plenty
# for a phone-sized basket; trigram scans per item stay fast at this scale.
MAX_STORES = 5
MAX_ITEMS = 20

_TOKEN_RE = re.compile(r"[^\W\d_]{3,}")
_STOP_TOKENS = {"and", "des", "les", "aux", "une", "avec", "pour", "from", "with"}


class BasketItem(BaseModel):
    name: str = Field(min_length=1, max_length=200, description='e.g. "2L 2% milk"')
    quantity: int = Field(default=1, ge=1)


class BasketRequest(BaseModel):
    lat: float
    lon: float
    radius_km: float = Field(default=10, gt=0, le=100)
    items: list[BasketItem] = Field(min_length=1, max_length=MAX_ITEMS)


class MatchedItem(BaseModel):
    requested: str
    quantity: int
    matched_name: str | None = None
    unit_price: float | None = None
    currency: str | None = None
    line_total: float | None = None


class StoreTotal(BaseModel):
    store: StoreOut
    items: list[MatchedItem]
    matched_count: int
    total: float
    unmatched: list[str]


class BasketTotals(BaseModel):
    stores: list[StoreTotal]


def _tokens(name: str) -> list[str]:
    words = [w for w in _TOKEN_RE.findall(name.lower()) if w not in _STOP_TOKENS]
    return words or [name.strip().lower()]


def _match_items_for_store(conn, store_id: str, items: list[BasketItem]) -> dict[int, dict]:
    """Best product per item at one store: one round-trip, ILIKE + trigram."""
    values_sql: list[str] = []
    params: dict = {"store_id": store_id}
    for idx, item in enumerate(items):
        values_sql.append(f"(:ordinal{idx}, :item{idx}, CAST(:pats{idx} AS text[]))")
        params[f"ordinal{idx}"] = idx
        params[f"item{idx}"] = item.name
        params[f"pats{idx}"] = [f"%{tok}%" for tok in _tokens(item.name)]

    query = text(f"""
        WITH wanted(ordinal, item, pats) AS (
            VALUES {", ".join(values_sql)}
        )
        SELECT
            wanted.ordinal,
            match.product_name,
            match.unit_price,
            match.currency,
            match.score
        FROM wanted
        LEFT JOIN LATERAL (
            SELECT
                p.name AS product_name,
                p.price AS unit_price,
                p.currency,
                (CASE
                    WHEN p.name ILIKE ANY(wanted.pats)
                        THEN 2.0 + similarity(p.name, wanted.item)
                    ELSE similarity(p.name, wanted.item)
                END) AS score
            FROM products p
            WHERE p.store_id = CAST(:store_id AS uuid)
              AND (p.name ILIKE ANY(wanted.pats) OR p.name % wanted.item)
            ORDER BY score DESC, p.price ASC
            LIMIT 1
        ) match ON true
        ORDER BY wanted.ordinal
    """)
    rows = conn.execute(query, params).mappings().all()
    return {row["ordinal"]: dict(row) for row in rows}


@router.post("/totals")
def basket_totals(body: BasketRequest) -> dict:
    """Per-store totals for the basket (matched items only, unmatched listed)."""
    try:
        with get_engine().connect() as conn:
            store_rows = (
                conn.execute(
                    NEARBY_SQL,
                    {
                        "lat": body.lat,
                        "lon": body.lon,
                        "radius_km": body.radius_km,
                        "limit": MAX_STORES,
                    },
                )
                .mappings()
                .all()
            )

            results: list[dict] = []
            for store in store_rows:
                matches = _match_items_for_store(conn, store["id"], body.items)
                items_out: list[dict] = []
                unmatched: list[str] = []
                total = 0.0
                for idx, item in enumerate(body.items):
                    match = matches.get(idx)
                    if match and match["product_name"]:
                        unit_price = float(match["unit_price"])
                        line_total = round(unit_price * item.quantity, 2)
                        total += line_total
                        items_out.append(
                            MatchedItem(
                                requested=item.name,
                                quantity=item.quantity,
                                matched_name=match["product_name"],
                                unit_price=unit_price,
                                currency=match["currency"],
                                line_total=line_total,
                            ).model_dump()
                        )
                    else:
                        unmatched.append(item.name)
                        items_out.append(
                            MatchedItem(requested=item.name, quantity=item.quantity).model_dump()
                        )
                results.append(
                    StoreTotal(
                        store=StoreOut.model_validate(store),
                        items=items_out,
                        matched_count=len(body.items) - len(unmatched),
                        total=round(total, 2),
                        unmatched=unmatched,
                    ).model_dump()
                )
        return {"stores": results}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
