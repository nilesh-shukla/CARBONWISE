"""Pytest fixtures for backend test suite."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Return test settings override."""
    return Settings(
        APP_ENV="testing",
        DEBUG=True,
    )


@pytest.fixture(scope="session")
def app(test_settings: Settings):
    """Return application instance configured for testing."""
    test_app = create_app(settings=test_settings)
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    return test_app


@pytest.fixture(scope="session")
def client(app) -> TestClient:
    """Return a TestClient instance for running API requests."""
    with TestClient(app) as test_client:
        yield test_client
