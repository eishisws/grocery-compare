"""Geocoding via Nominatim (free). To swap to Mapbox, change this one file —
the response shape (list of {label, lat, lon}) is the only contract.
"""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/geocode", tags=["geocode"])


class GeocodeHit(BaseModel):
    label: str
    lat: float
    lon: float


@router.get("", response_model=list[GeocodeHit])
async def geocode(q: str) -> list[GeocodeHit]:
    """Resolve a postal code or address into coordinates for store lookup."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.nominatim_base_url}/search",
                params={"q": q, "format": "jsonv2", "limit": 5},
                headers={"User-Agent": settings.user_agent},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Geocoder unavailable") from exc

    return [
        GeocodeHit(label=item["display_name"], lat=float(item["lat"]), lon=float(item["lon"]))
        for item in resp.json()
    ]
