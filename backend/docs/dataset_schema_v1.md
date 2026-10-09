# Synthetic Household Dataset — Schema v1
**CARBONWISE | Stage C1 Design**  
_India-focused | Monthly reporting period | Design-only — no records generated here_

---

## 1. ML Task and Leakage Boundary

| Item | Decision |
|---|---|
| **Task** | Estimate a household's monthly CO2 emissions (kg CO2/month) from household and lifestyle **descriptors** — without consumption amount inputs (kWh, kg). |
| **Inputs (X)** | Household and lifestyle descriptors (14 fields, see Section 3). |
| **Intermediates** | `electricity_kwh_per_month`, `lpg_kg_per_month` — synthetically generated during dataset construction; **not model inputs**. |
| **Targets (y)** | `total_emissions_kg_co2`, `direct_emissions_kg_co2`, `indirect_emissions_kg_co2` — computed via `CarbonCalculatorService`. |
| **Leakage rule** | No X-field may encode consumption amounts or derived emissions directly. Appliance-ownership fields indicate capability (probabilistic proxy), not metered usage. |

---

## 2. Emission Factor Scope

Only factors with `status: verified` in `data/emission_factors/factors.yaml`:

| Activity | Factor ID | Value | Unit |
|---|---|---|---|
| Electricity | `electricity_grid_india_cea` | 0.716 | kgCO2/kWh |
| LPG | `lpg_stationary_ipcc_2006` | 2.98463 | kgCO2/kg |

Petrol and diesel (both `status: unresolved`) are excluded from targets.

---

## 3. Schema v1 — Field Definitions

> All parameters tagged `[assumption]` unless the value is already documented in the repo `[repo]`.

### 3.1 Record Metadata (1 field)

| Field | Type | Values / Range | Tag |
|---|---|---|---|
| `record_id` | `str` (UUID v4) | — | `[assumption]` |

### 3.2 Household Descriptors (5 fields)

| Field | Type | Values / Range | Tag |
|---|---|---|---|
| `household_size` | `int` | 1–10 | `[assumption]` |
| `dwelling_type` | enum | `apartment`, `independent_house`, `chawl_shared` | `[assumption]` |
| `settlement_type` | enum | `urban`, `peri_urban`, `rural` | `[assumption]` |
| `state` | enum | ISO 3166-2:IN codes (36 states + UTs) | `[assumption]` |
| `monthly_household_income_band` | enum | `<10k`, `10k-25k`, `25k-50k`, `50k-100k`, `>100k` (INR/month) | `[assumption]` |

### 3.3 Lifestyle / Occupancy Descriptors (5 fields)

| Field | Type | Values / Range | Tag |
|---|---|---|---|
| `daytime_occupancy_hours` | `float` | 0.0–24.0 | `[assumption]` |
| `cooking_fuel_primary` | enum | `lpg`, `electricity`, `biomass`, `piped_gas`, `none` | `[assumption]` |
| `cooking_fuel_secondary` | enum | `lpg`, `electricity`, `biomass`, `none` | `[assumption]` |
| `num_working_members` | `int` | 0–6 | `[assumption]` |
| `climate_zone` | enum | `hot_dry`, `warm_humid`, `composite`, `temperate`, `cold` | `[assumption]` |

### 3.4 Appliance Ownership — Capability Proxies (4 fields)

> These fields indicate whether an appliance is owned, NOT how much electricity it uses.

| Field | Type | Values | Tag |
|---|---|---|---|
| `has_air_conditioner` | `bool` | True / False | `[assumption]` |
| `has_refrigerator` | `bool` | True / False | `[assumption]` |
| `has_washing_machine` | `bool` | True / False | `[assumption]` |
| `has_personal_vehicle` | `bool` | True / False | `[assumption]` |

> `has_personal_vehicle` is included for future transport scope; not used in Stage B targets.

### 3.5 Generated Intermediates (2 fields — stored, NOT model inputs)

> Must be dropped before model training.

| Field | Type | Unit | Tag |
|---|---|---|---|
| `electricity_kwh_per_month` | `float` | kWh | `[assumption]` |
| `lpg_kg_per_month` | `float` | kg | `[assumption]` |

### 3.6 Target Variables (3 fields — labels)

> Computed by `CarbonCalculatorService.calculate()` from the intermediates.

| Field | Type | Unit | Source |
|---|---|---|---|
| `total_emissions_kg_co2` | `float` | kgCO2/month | `[repo]` `CalculationResponse.total_emissions_kg_co2` |
| `direct_emissions_kg_co2` | `float` | kgCO2/month | `[repo]` `CalculationResponse.direct_emissions_kg_co2` |
| `indirect_emissions_kg_co2` | `float` | kgCO2/month | `[repo]` `CalculationResponse.indirect_emissions_kg_co2` |

---

## 4. Field Count Summary

| Group | Count | Role |
|---|---|---|
| Metadata | 1 | Identifier |
| Household descriptors | 5 | X |
| Lifestyle / occupancy | 5 | X |
| Appliance ownership | 4 | X |
| **Total X (model inputs)** | **14** | |
| Generated intermediates | 2 | Stored, not X |
| Targets | 3 | y |
| **Total fields in dataset file** | **20** | |

---

## 5. Schema Implementation (Stage C2)

- Pydantic model: `backend/app/schemas/dataset.py` → `SyntheticHouseholdRecord`
- Generation script: `backend/scripts/generate_synthetic_data.py`
- Output: `backend/data/synthetic/household_records_v1.csv`
- Tests: `backend/tests/test_dataset_schema.py` (schema validation + leakage guard)

---

## 6. Open Issues

| # | Issue | Status |
|---|---|---|
| 1 | State-level grid emission factors | Deferred; default region = `India` |
| 2 | `cooking_fuel_secondary` class imbalance | Keep field; mark optional |
| 3 | `has_personal_vehicle` unused in Stage B | Keep for future extension |
| 4 | Intermediate generation distributions | Defined in Stage C2 |
| 5 | Dataset size | Deferred to Stage C2 (estimated 5k–50k records) |
| 6 | Petrol/diesel intermediates | Excluded; re-evaluated when factors resolved |
