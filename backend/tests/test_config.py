"""Tests for deployment-sensitive application configuration."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_debug_defaults_to_false() -> None:
    settings = Settings(APP_ENV="development")

    assert settings.DEBUG is False


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        Settings(APP_ENV="production", DEBUG=True)


def test_production_allows_debug_off() -> None:
    settings = Settings(APP_ENV="production", DEBUG=False)

    assert settings.DEBUG is False
