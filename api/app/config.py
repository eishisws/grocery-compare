from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/grocery"

    # Geocoding (swap Mapbox in by editing routers/geocode.py)
    geocoding_provider: str = "nominatim"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    user_agent: str = "grocery-compare/0.1 (github.com/you/grocery-compare)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
