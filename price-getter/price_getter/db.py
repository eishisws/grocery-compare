from sqlalchemy import create_engine

from price_getter.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
