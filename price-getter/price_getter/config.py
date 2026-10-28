from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/grocery"

    # LLM used to parse messy lists and settle close product matches.
    # Any OpenAI-compatible API works: set llm_base_url to point at it
    # (empty = OpenAI itself). Free tiers: Groq, Google Gemini, OpenRouter.
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = ""
    openai_api_key: str = ""

    @field_validator("llm_model", mode="before")
    @classmethod
    def _default_llm_model(cls, value: str) -> str:
        # CI may set an empty-string env var when a secret/var is missing;
        # fall back to the default model instead of overriding with ""
        return value or "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()
