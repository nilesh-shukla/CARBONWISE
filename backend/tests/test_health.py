"""Tests for the health check endpoint."""

from fastapi import status
from fastapi.testclient import TestClient

from app import __version__


def test_health_check_status_and_schema(client: TestClient) -> None:
    """Test that GET /health returns 200 OK with expected fields."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "status" in data
    assert "app_name" in data
    assert "version" in data
    assert "environment" in data

    assert data["status"] == "healthy"
    assert data["version"] == __version__
    assert data["environment"] == "testing"


def test_health_check_v1_route(client: TestClient) -> None:
    """Test that GET /api/v1/health also returns 200 OK and valid health payload."""
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == __version__
