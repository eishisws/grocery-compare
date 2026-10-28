from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/grocery"

    # LLM used to parse messy lists and settle close product matches
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
