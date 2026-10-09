# System Architecture & Academic Project Overview

## Project Title
**A Data-Driven Estimation Model for Personalized Household Carbon Footprints Using Synthetic Lifestyle and Consumption Data**

## Architecture Design
The backend is designed using a clean, layered architectural pattern ensuring separation of concerns:

```
[ Client Request ]
       │
       ▼
[ FastAPI App Factory (app/main.py) ]
  ├── Global Error Handling (Validation, HTTP, Internal)
  ├── CORS & Middleware Layer (Future)
  └── Routing Layer (app/api/v1/)
       │
       ├── health.py  ──> System status & versioning
       └── root.py    ──> Service description & /docs
       │
       ▼ (Future Phases)
[ Services Layer (app/services/) ]
  ├── Synthetic Data Generation Service
  └── Deterministic Footprint Calculator (Cited Emission Factors)
       │
       ▼ (Future Phases)
[ ML Estimation Engine (app/ml/) ]
  ├── Feature Extraction Pipelines
  └── Trained Scikit-Learn Model Inference
       │
       ▼
[ Data Layer (data/) ]
  ├── emission_factors/ (Strictly cited IPCC/EPA/DEFRA/CEA factors)
  ├── synthetic/        (Generated lifestyle/consumption datasets)
  ├── raw/              (Baseline demographic & consumption benchmarks)
  └── processed/        (Cleaned & normalized training features)
```

## Phase Progression Roadmap
1. **Phase 1 (Current - Scaffolding)**:
   - Establish clean modular layout.
   - Configure centralized settings and single source of truth for versioning.
   - Standardize global error formats and response schemas.
   - Implement `/health` and `/` endpoints with comprehensive test suite.
2. **Phase 2 (Data Modeling & Synthetic Generation)**:
   - Construct cited emission factor tables with strict metadata schema.
   - Develop synthetic lifestyle profile generation algorithms using statistical distributions.
3. **Phase 3 (Deterministic Engine)**:
   - Implement baseline deterministic calculation services mapping activity inputs to CO2e emissions.
4. **Phase 4 (Machine Learning & Serving)**:
   - Train scikit-learn models on synthetic and benchmarked data for rapid personalized estimation.
   - Serve model inference endpoints via FastAPI.
