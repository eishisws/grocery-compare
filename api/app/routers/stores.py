"""Stores near a point, via PostGIS `ST_DWithin` + gist index on
`stores.location` (see database/schema.sql).
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_engine

router = APIRouter(prefix="/stores", tags=["stores"])

NEARBY_SQL = text("""
    SELECT
        id::text,
        name,
        chain,
        address,
        ST_Y(location::geometry) AS lat,
        ST_X(location::geometry) AS lon,
        ST_Distance(location, ST_MakePoint(:lon, :lat)::geography) / 1000.0 AS distance_km
    FROM stores
    WHERE ST_DWithin(
        location,
        ST_MakePoint(:lon, :lat)::geography,
        :radius_km * 1000.0
    )
    ORDER BY distance_km
    LIMIT :limit
""")


class StoreOut(BaseModel):
    id: str
    name: str
    chain: str | None = None
    address: str | None = None
    lat: float
    lon: float
    distance_km: float


@router.get("/nearby", response_model=list[StoreOut])
def nearby_stores(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(10, gt=0, le=100),
    limit: int = Query(20, ge=1, le=50),
) -> list[StoreOut]:
    """Stores within `radius_km` of a point, sorted by distance."""
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                NEARBY_SQL, {"lat": lat, "lon": lon, "radius_km": radius_km, "limit": limit}
            )
            return [StoreOut.model_validate(row._mapping) for row in rows]
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
