"""Tests for the root information endpoint."""

from fastapi import status
from fastapi.testclient import TestClient

from app import __version__


def test_root_status_and_schema(client: TestClient) -> None:
    """Test that GET / returns 200 OK with expected fields and docs link."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "description" in data
    assert "docs_url" in data

    assert data["version"] == __version__
    assert data["docs_url"] == "/docs"
    assert len(data["description"]) > 0


def test_root_v1_route(client: TestClient) -> None:
    """Test that GET /api/v1/ also returns 200 OK and valid root metadata."""
    response = client.get("/api/v1/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["docs_url"] == "/docs"
    assert data["version"] == __version__
