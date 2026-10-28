from functools import lru_cache

from sqlalchemy import Engine, create_engine

from price_getter.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Lazily built engine for the write side. Postgres is this prong's only
    interface — the API reads what ends up here and nothing else."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)
