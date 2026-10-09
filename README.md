# CARBONWISE

> **A Data-Driven Estimation Model for Personalized Household Carbon Footprints Using Synthetic Lifestyle and Consumption Data**

## Repository Organization
The project is split into distinct backend and frontend directories:

```text
CARBONWISE/
├── backend/    # FastAPI backend, data pipelines, ML estimators, and automated tests
└── frontend/   # User interface and client application workspace (future phase)
```

## Backend Quickstart (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt

# Run automated tests
pytest

# Start the local development server
uvicorn app.main:app --reload
```

For comprehensive backend architecture details, environment configurations, and file descriptions, see the [backend/README.md](file:///d:/Projects/CARBONWISE/backend/README.md).
