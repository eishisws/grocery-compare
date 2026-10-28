from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Lazily built engine — routers grab it per request; tests can repoint the
    DATABASE_URL it reads. Postgres is the prong's only dependency."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)
