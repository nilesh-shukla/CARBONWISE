# Household Carbon Footprint Backend

> **Academic Project**: *A Data-Driven Estimation Model for Personalized Household Carbon Footprints Using Synthetic Lifestyle and Consumption Data.*

## 1. Project Overview
This backend provides the API and research infrastructure for household carbon-footprint
estimation. It includes a synthetic household dataset, a deterministic emissions calculator,
and a bounded scikit-learn experiment that predicts generated electricity and LPG consumption
from household/lifestyle descriptors. It does not currently serve an ML prediction model.

All ML metrics documented here are **synthetic-data results only**. The generator's assumptions
have not been empirically calibrated against household consumption data; results do not establish
accuracy for actual Indian households or population representativeness. See
[`docs/dataset_schema_v1.md`](docs/dataset_schema_v1.md) for the complete schema and generation
assumptions.

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

## 5. Synthetic ML Experiment Record (C3.3)

### Prediction contract and leakage boundary

The experiment uses the 10,000-row `data/synthetic/household_records_v1.csv` dataset. Its
14 descriptor inputs are exactly the `MODEL_INPUT_FIELDS` allowlist in
`app/schemas/dataset.py`:

| Feature | Type |
|---|---|
| `household_size` | Integer |
| `dwelling_type` | Categorical |
| `settlement_type` | Categorical |
| `state` | Categorical |
| `monthly_household_income_band` | Categorical |
| `daytime_occupancy_hours` | Numeric |
| `cooking_fuel_primary` | Categorical |
| `cooking_fuel_secondary` | Categorical |
| `num_working_members` | Integer |
| `climate_zone` | Categorical |
| `has_air_conditioner` | Boolean |
| `has_refrigerator` | Boolean |
| `has_washing_machine` | Boolean |
| `has_personal_vehicle` | Boolean |

The two prediction targets are `electricity_kwh_per_month` (kWh/month) and
`lpg_kg_per_month` (kg/month). LPG is evaluated in two parts: LPG use (`lpg > 0`) is a
binary classification task; the positive-LPG amount task is scored only on records that
actually use LPG. A two-stage result combines the predicted use class and positive-use amount
to score LPG quantity across all records.

The model feature matrix excludes the five metadata fields (`record_id`, `schema_version`,
`generation_run_id`, `random_seed`, `is_synthetic`), both activity quantities when they are
used as targets, and all three calculator outputs (`total_emissions_kg_co2`,
`direct_emissions_kg_co2`, `indirect_emissions_kg_co2`). Emissions are deterministic outputs
of `CarbonCalculatorService.calculate()` from activity quantities, not independent household
observations. Petrol and diesel remain unresolved and are outside this dataset's targets.

### Protocol and frozen configurations

The dataset generation seed and the split seed were both **42**. The row-level split is
stratified by LPG use into 70% training, 15% validation, and 15% held-out test:

| Partition | Rows | LPG users | Zero-LPG records |
|---|---:|---:|---:|
| Train | 7,000 | 2,104 | 4,896 |
| Validation | 1,500 | 451 | 1,049 |
| Test | 1,500 | 451 | 1,049 |

Categorical features use one-hot encoding with unknown categories ignored. Numeric features
use `StandardScaler` for Ridge and logistic regression, and pass through unchanged for random
forests. Each transform is fitted on training rows only. Positive-LPG regressors are fitted
only on positive-LPG training rows (2,104 records); their conditional amount metrics use actual
positive-LPG evaluation records.

Baselines are training-derived: mean and median electricity; majority-class LPG use; mean and
median LPG amount among positive-use training records; and training mean/median LPG amount for
the two-stage all-record comparison. In that two-stage comparison, each training-wide mean or
median is a single constant prediction applied to every evaluation row, including zero-LPG
records; it is not a classifier-plus-regressor baseline. The separate positive-LPG amount
baselines are fit on positive-use training rows and scored only on actual positive-use rows.
Candidate configurations were declared before evaluation:

| Task | Model | Configuration |
|---|---|---|
| Electricity | Ridge | `alpha=1.0` |
| Electricity | RandomForestRegressor | `n_estimators=100`, `max_depth=12`, `min_samples_leaf=5`, `max_features=1.0`, `n_jobs=1`, `random_state=42` |
| LPG use | LogisticRegression | `C=1.0`, `max_iter=1000`, `solver=lbfgs`, `random_state=42` |
| LPG use | RandomForestClassifier | `n_estimators=100`, `max_depth=12`, `min_samples_leaf=5`, `max_features=1.0`, `n_jobs=1`, `random_state=42` |
| Positive LPG amount | Ridge | `alpha=1.0` |
| Positive LPG amount | RandomForestRegressor | `n_estimators=100`, `max_depth=12`, `min_samples_leaf=5`, `max_features=1.0`, `n_jobs=1`, `random_state=42` |

The configurations were compared on validation data before the final test evaluation. All six
predeclared configurations were carried forward as a frozen finalist set because no formal
single-winner rule was recorded. The test partition was used only for the final reported
metrics; it was not used for fitting preprocessing, tuning, or model selection. These scores
evaluate held-out rows from the same synthetic generation process, not a new generator run or
real households.

### Validation results — synthetic data only

Mean absolute error (MAE) and root mean squared error (RMSE) are reported in the target unit.
Electricity and all-record LPG metrics use 1,500 rows; LPG-use classification uses 1,500 rows
(451 positive, 1,049 zero); positive-LPG amount metrics use 451 actual LPG users.

| Task / model | MAE | RMSE | Classification metrics |
|---|---:|---:|---|
| Electricity mean baseline (kWh/month) | 208.477 | 282.524 | — |
| Electricity median baseline (kWh/month) | 195.418 | 293.604 | — |
| Electricity Ridge (kWh/month) | 177.487 | 247.993 | — |
| Electricity random forest (kWh/month) | 177.459 | 250.598 | — |
| LPG-use majority baseline | — | — | Precision undefined; recall 0.000; F1 0.000 |
| LPG-use logistic regression | — | — | Precision 1.000; recall 1.000; F1 1.000 |
| LPG-use random forest | — | — | Precision 1.000; recall 1.000; F1 1.000 |
| Positive LPG mean baseline (kg/month) | 9.292 | 11.857 | — |
| Positive LPG median baseline (kg/month) | 9.056 | 12.167 | — |
| Positive LPG Ridge (kg/month) | 6.898 | 9.321 | — |
| Positive LPG random forest (kg/month) | 6.808 | 9.480 | — |
| Two-stage logistic + Ridge LPG (kg/month, all rows) | 2.074 | 5.111 | — |
| Two-stage random forest LPG (kg/month, all rows) | 2.047 | 5.198 | — |

The validation report recorded two-stage baseline comparisons as candidate-minus-baseline
deltas rather than standalone baseline scores. For logistic + Ridge, the MAE/RMSE deltas were
−5.1526/−5.0510 against the training mean and −3.0483/−6.2685 against the training median.
For the random forest pair, the deltas were −5.1795/−4.9639 against the mean and
−3.0752/−6.1814 against the median. Each baseline constant was applied to all 1,500 validation
rows, including zero-LPG records.

For both validation LPG classifiers, the confusion matrix (actual rows and predicted columns,
labels `[0, 1]`) was `[[1049, 0], [0, 451]]`. The use/no-use label is directly determined by
the synthetic cooking-fuel rules, including the LPG-use categories. Perfect classification
therefore demonstrates recovery of a generator rule, not real-world accuracy.

### Final held-out test results — synthetic data only

The following results use the untouched 1,500-row test partition from the same seed-42 split.
Electricity and two-stage LPG metrics use all 1,500 rows; positive-LPG amount metrics use the
451 actual LPG users. LPG-use classification uses all 1,500 rows (451 positive, 1,049 zero).

| Task / model | MAE | RMSE | Classification metrics |
|---|---:|---:|---|
| Electricity mean baseline (kWh/month) | 215.363 | 299.365 | — |
| Electricity median baseline (kWh/month) | 208.796 | 315.078 | — |
| Electricity Ridge (kWh/month) | 178.771 | 257.518 | — |
| Electricity random forest (kWh/month) | 178.243 | 255.334 | — |
| LPG-use majority baseline | — | — | Precision undefined; recall 0.000; F1 0.000 |
| LPG-use logistic regression | — | — | Precision 1.000; recall 1.000; F1 1.000 |
| LPG-use random forest | — | — | Precision 1.000; recall 1.000; F1 1.000 |
| Positive LPG mean baseline (kg/month) | 9.010 | 11.511 | — |
| Positive LPG median baseline (kg/month) | 8.858 | 11.836 | — |
| Positive LPG Ridge (kg/month) | 6.202 | 8.695 | — |
| Positive LPG random forest (kg/month) | 6.217 | 8.651 | — |
| Two-stage training-mean LPG baseline (kg/month, all rows) | 7.209 | 10.051 | — |
| Two-stage training-median LPG baseline (kg/month, all rows) | 5.130 | 11.284 | — |
| Two-stage logistic + Ridge LPG (kg/month, all rows) | 1.865 | 4.768 | — |
| Two-stage random forest LPG (kg/month, all rows) | 1.869 | 4.743 | — |

Each test LPG classifier had confusion matrix `[[1049, 0], [0, 451]]` (actual rows, predicted
columns; labels `[0, 1]`). The same generator-rule explanation applies. These results are
synthetic-only and must not be presented as validated predictions of real household behavior.

### Interpretation and limitations

- The dataset has 10,000 generated records; distribution parameters, sampling weights, and
  descriptor/activity relationships are documented design assumptions, not empirically
  calibrated household-consumption relationships.
- No empirical household dataset was used for calibration or external validation. A random
  held-out split and the synthetic results do not establish real-world accuracy, causal effects,
  personalization validity, or representativeness of Indian households.
- All records assume positive grid electricity use; off-grid households are not represented
  by the v1 generator. Transport emissions are also outside scope while petrol/diesel factors
  remain unresolved.
- Emissions can be derived from activity predictions with the existing deterministic
  calculator, but they are not independent ground-truth observations.

The validation and final-test reports can be produced from the backend directory with:

```powershell
python -m scripts.run_ml_baselines --compare-models --split-seed 42
python -m scripts.run_ml_baselines --final-test --split-seed 42
```

The final-test command is for the recorded final evaluation protocol; do not use test metrics
to tune or select configurations.

---

## 6. Running the Tests

Execute the automated test suite with `pytest`:

```powershell
pytest -q
```

To run with verbose output:
```powershell
pytest -v
```

---

## 7. Project File Manifest

| Path | Purpose |
| :--- | :--- |
| `pyproject.toml` | Build and project metadata configuration, pytest settings, and linting standards. |
| `requirements.txt` | Runtime dependencies (FastAPI, Uvicorn, Pydantic, pydantic-settings, Pandas, NumPy, scikit-learn, PyYAML). |
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
| `app/ml/experiment.py` | Validated dataset loading, deterministic splitting, baselines, and leakage-safe ML evaluation. |
| `data/emission_factors/factors.yaml` | Traceable emission factor registry file with full citation metadata. |
| `data/emission_factors/README.md`| Citation rules and required metadata schema for verified emission factors. |
| `data/synthetic/household_records_v1.csv` | 10,000-row synthetic household dataset; not a representative population sample. |
| `docs/dataset_schema_v1.md` | Dataset field contract, generation assumptions, and leakage boundary. |
| `scripts/generate_synthetic_data.py` | Reproducible synthetic household dataset generator. |
| `scripts/run_ml_baselines.py` | Baseline, validation-comparison, and final held-out test CLI. |
| `data/raw/.gitkeep` | Placeholder directory for baseline external surveys and consumption benchmarks. |
| `data/synthetic/.gitkeep` | Directory marker retained alongside the generated v1 synthetic dataset. |
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
