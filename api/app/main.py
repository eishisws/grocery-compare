from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import basket, geocode, stores

app = FastAPI(
    title="Grocery Compare API",
    version="0.1.0",
    description=(
        "Client-facing prong: resolve a location, find stores within a radius, "
        "total a basket per store. The database is the single source of truth; "
        "this service never calls price-getter and reads Postgres only."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # frontend dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(geocode.router)
app.include_router(stores.router)
app.include_router(basket.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
