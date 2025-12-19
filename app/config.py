"""Application configuration."""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_env: str = "development"
    database_url: str

    # Redis (for Celery)
    redis_url: str = "redis://localhost:6379/0"

    # Supabase
    supabase_url: str
    supabase_service_role_key: str

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
