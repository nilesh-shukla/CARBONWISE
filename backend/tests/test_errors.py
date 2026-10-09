"""Tests for global error handling and response formatting."""

from fastapi import Query, status
from fastapi.testclient import TestClient


def test_404_not_found_standardized_error(client: TestClient) -> None:
    """Test that requesting an unknown route returns consistent 404 JSON error."""
    response = client.get("/nonexistent-endpoint-xyz")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    payload = response.json()
    assert "error" in payload
    error = payload["error"]

    assert error["code"] == "NOT_FOUND"
    assert "Not Found" in error["message"] or len(error["message"]) > 0


def test_405_method_not_allowed_standardized_error(client: TestClient) -> None:
    """Test that using an invalid HTTP method returns consistent 405 JSON error."""
    response = client.post("/health")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    payload = response.json()
    assert "error" in payload
    error = payload["error"]

    assert error["code"] == "METHOD_NOT_ALLOWED"
    assert "Method Not Allowed" in error["message"]


def test_validation_error_standardized_format(app, client: TestClient) -> None:
    """Test that schema validation errors return consistent 422 JSON error."""

    @app.get("/_test/validation-check")
    def _dummy_route(number: int = Query(...)):
        return {"number": number}

    response = client.get("/_test/validation-check?number=invalid_string")
    assert response.status_code == 422

    payload = response.json()
    assert "error" in payload
    error = payload["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Request validation failed."
    assert isinstance(error["details"], list)
    assert len(error["details"]) > 0
    assert "number" in str(error["details"][0]["location"])
