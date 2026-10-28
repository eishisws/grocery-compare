"""Basket totals: per nearby store, sum of the best matching product per item.

Matching strategy (in priority order):
1. Exact/ILIKE name hit — implemented once the price-getter writes normalized names
2. Embedding kNN via pgvector — needs products.embedding populated
3. LLM settle between close candidates — same dependency

The request/response shape is frozen now so the frontend can build against it;
it returns 501 until the price-getter has populated products.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/basket", tags=["basket"])


class BasketItem(BaseModel):
    name: str = Field(min_length=1, description='e.g. "2L 2% milk", "500g butter"')
    quantity: int = Field(default=1, ge=1)


class BasketRequest(BaseModel):
    lat: float
    lon: float
    radius_km: float = Field(default=10, gt=0, le=100)
    items: list[BasketItem] = Field(min_length=1)


@router.post("/totals")
def basket_totals(body: BasketRequest) -> dict:
    """Per-store totals for the basket."""
    raise HTTPException(
        status_code=501,
        detail=(
            "Basket matching is not wired yet: it needs normalized products and "
            "embeddings written by the price-getter. Shape is stable — build against it."
        ),
    )
