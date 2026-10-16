"""Application configuration loaded via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__


class Settings(BaseSettings):
    """Configuration settings for the application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "Household Carbon Footprint Estimation API"
    APP_VERSION: str = __version__
    APP_ENV: Literal["development", "testing", "production"] = "development"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEFAULT_REGION: str = "India"
    FACTORS_FILE_PATH: str = "data/emission_factors/factors.yaml"

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        """Reject unsafe debug settings in production."""
        if self.APP_ENV == "production" and self.DEBUG:
            raise ValueError("DEBUG must be false when APP_ENV=production")
        return self

    @property
    def factors_path(self) -> Path:
        """Resolve path to factors.yaml relative to backend directory."""
        path = Path(self.FACTORS_FILE_PATH)
        if not path.is_absolute():
            backend_root = Path(__file__).resolve().parent.parent.parent
            path = backend_root / path
        return path


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""
    return Settings()
