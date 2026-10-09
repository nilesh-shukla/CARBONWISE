# Household Carbon Footprint Backend

> **Academic Project**: *A Data-Driven Estimation Model for Personalized Household Carbon Footprints Using Synthetic Lifestyle and Consumption Data.*

## 1. Project Overview
This service provides the backend foundation for personalized household carbon footprint estimation. 

In subsequent project phases, the system will:
1. Accept household lifestyle and consumption inputs across energy, transport, diet, and waste.
2. Generate synthetic lifestyle and consumption profiles using parametric statistical models.
3. Compute deterministic carbon emissions using strictly cited emission factors.
4. Train and serve a personalized machine learning estimation model (using scikit-learn).

This initial phase establishes clean architectural scaffolding, standardized configuration via `pydantic-settings`, global error handling, and tested entry-point endpoints.

---

## 2. Environment & Prerequisites
- **Operating System**: Windows (commands below use PowerShell; also compatible with macOS/Linux)
- **Python**: Python 3.11+ (verified on Python 3.13)
- **Package Manager**: `pip` with `venv`

---

## 3. Setup & Installation (Windows PowerShell)

All commands should be executed from within the `backend/` directory:

```powershell
# Navigate to the backend directory
cd backend

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip (recommended)
python -m pip install --upgrade pip

# Install runtime and development dependencies
pip install -r requirements.txt -r requirements-dev.txt

# (Optional) Copy example environment configuration
Copy-Item .env.example .env
```

> **Note on PowerShell Execution Policy**: If you encounter a script execution restriction when activating `.venv`, run:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## 4. Running the Application

Start the development server with Uvicorn:

```powershell
# Using the activated virtual environment
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Once running:
- **Root Info**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Calculate Footprint**: [POST http://127.0.0.1:8000/api/v1/calculate](http://127.0.0.1:8000/docs#/Calculation/calculate_footprint_api_v1_calculate_post)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### Calculation API Semantics (`POST /api/v1/calculate`)
- **Status Semantics**:
  - `complete_for_provided_inputs`: Every supplied activity was successfully calculated (`total_is_partial: false`).
  - `partial`: At least one supplied activity could not be calculated due to unresolved factors (`total_is_partial: true`).
  - Omitted activities do not make the result partial and are returned under `not_provided_categories`.
- **Zero Input Handling**: An omitted input (`null`) represents "not provided". An explicit `0.0` represents an "explicit zero supplied by the user" (yielding zero emissions for calculable activities). If supplied for an unresolved factor (petrol/diesel), it is marked `not_calculated` and excluded.
- **Footprint Scope Disclaimer**: The total covers only the supplied, calculable activities and is not a full household footprint.

---

## 5. Running the Tests

Execute the automated test suite with `pytest`:

```powershell
pytest -q
```

To run with verbose output:
```powershell
pytest -v
```

---

## 6. Project File Manifest

| Path | Purpose |
| :--- | :--- |
| `pyproject.toml` | Build and project metadata configuration, pytest settings, and linting standards. |
| `requirements.txt` | Runtime dependencies (FastAPI, Uvicorn, Pydantic, pydantic-settings, Pandas, NumPy, PyYAML). |
| `requirements-dev.txt` | Development dependencies (Pytest, HTTPX, Ruff). |
| `.env.example` | Template for environment variable configurations. |
| `.gitignore` | Ignores virtual environments, caches, compiled binaries, and sensitive files. |
| `README.md` | Backend documentation, setup instructions, commands, and file manifest. |
| `app/__init__.py` | Package root defining `__version__ = "0.1.0"` as the single source of truth. |
| `app/main.py` | FastAPI application factory `create_app()` with standardized error handlers. |
| `app/core/__init__.py` | Package initializer for core configuration and settings. |
| `app/core/config.py` | Application configuration loaded via `pydantic-settings` from environment variables. |
| `app/schemas/__init__.py` | Exposes response and error schema models for external consumption. |
| `app/schemas/common.py` | Pydantic models for standardized error payloads (`ErrorResponse`, `ErrorBody`). |
| `app/schemas/calculate.py` | Pydantic models for calculation request and response contracts. |
| `app/schemas/health.py` | Pydantic response schema for `/health` endpoint (`HealthResponse`). |
| `app/schemas/root.py` | Pydantic response schema for `/` endpoint (`RootResponse`). |
| `app/api/__init__.py` | API package initializer. |
| `app/api/v1/__init__.py` | Version 1 API package initializer. |
| `app/api/v1/router.py` | Aggregates all v1 endpoint routers. |
| `app/api/v1/endpoints/__init__.py` | Endpoints subpackage initializer. |
| `app/api/v1/endpoints/calculate.py` | Route handler for `POST /api/v1/calculate`. |
| `app/api/v1/endpoints/health.py` | Route handler for `GET /health` (and `/api/v1/health`). |
| `app/api/v1/endpoints/root.py` | Route handler for `GET /` (and `/api/v1/`). |
| `app/services/__init__.py` | Services package initializer and exports. |
| `app/services/exceptions.py` | Domain-specific exceptions (`FactorNotFoundError`, `UnresolvedFactorError`, etc.). |
| `app/services/registry.py` | Traceable emission factor registry loader and validator. |
| `app/services/calculator.py` | Deterministic carbon calculation service implementation. |
| `app/ml/__init__.py` | Placeholder package for future scikit-learn models and training pipelines. |
| `data/emission_factors/factors.yaml` | Traceable emission factor registry file with full citation metadata. |
| `data/emission_factors/README.md`| Citation rules and required metadata schema for verified emission factors. |
| `data/raw/.gitkeep` | Placeholder directory for baseline external surveys and consumption benchmarks. |
| `data/synthetic/.gitkeep` | Placeholder directory for generated lifestyle and consumption datasets. |
| `data/processed/.gitkeep` | Placeholder directory for curated and normalized training features. |
| `docs/architecture.md` | Architectural design diagrams and phased development roadmap. |
| `scripts/__init__.py` | Standalone operational scripts and batch processing utilities. |
| `tests/__init__.py` | Test package initializer. |
| `tests/conftest.py` | Pytest fixtures providing configured `app` and `TestClient` instances. |
| `tests/test_calculator.py` | Hand-calculated tests, zero consumption, invalid inputs, and total sum tests. |
| `tests/test_registry.py` | Unit tests for emission factor registry loading, verification, and errors. |
| `tests/test_health.py` | Unit and integration tests for `/health` endpoint schema and status. |
| `tests/test_root.py` | Unit and integration tests for `/` endpoint schema and documentation links. |
| `tests/test_errors.py` | Verification of centralized 404, 405, and 422 error handling formatting. |
