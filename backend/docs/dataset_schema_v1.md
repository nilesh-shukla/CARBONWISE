# Synthetic Household Dataset — Schema v1
**CARBONWISE | Stage C1 + C1.1 Decisions**
_India-focused | Monthly reporting period | Schema and generation defaults for v1_

> **Methodology disclaimer (state once, apply everywhere):**
> All distribution parameters, sampling weights, and dependency rationales in this document
> are design assumptions requiring empirical calibration. Nothing here is claimed to represent
> India's actual household population, to be statistically validated, or to constitute a
> nationally representative sample.

---

## 1. Dataset Roles and ML Leakage Boundary

| Item | Decision |
|---|---|
| **Current C3.3 experiment** | Predict monthly electricity consumption and LPG consumption from household/lifestyle descriptors only. These are two activity-prediction tasks; see the backend README's ML experiment record for protocols and reported results. |
| **Inputs (X)** | The 14 descriptor fields in `MODEL_INPUT_FIELDS` (Section 7). This allowlist is authoritative. |
| **Activity quantities** | `electricity_kwh_per_month` and `lpg_kg_per_month` are synthetically generated. They are the supervised targets (y) for the C3.3 descriptor-only consumption tasks, and must not be included in X. |
| **Derived emissions** | `total_emissions_kg_co2`, `direct_emissions_kg_co2`, and `indirect_emissions_kg_co2` are computed deterministically by `CarbonCalculatorService` from activity quantities. They are not independent observations and are not targets in the C3.3 ML experiment. |
| **Leakage rule** | Keep all activity quantities, emissions outputs, identifiers, run metadata, and calculator response metadata out of X. Appliance-ownership fields indicate capability, not metered usage. Cooking-fuel fields are intended descriptor signals; the generator uses them to determine LPG use, so perfect LPG-use classification reflects that synthetic rule rather than empirical predictive validity. |

---

## 2. Emission Factor Scope

Only factors with `status: verified` in `data/emission_factors/factors.yaml` are used to compute targets:

| Activity | Factor ID | Value | Unit | Source |
|---|---|---|---|---|
| Electricity | `electricity_grid_india_cea` | 0.716 | kgCO2/kWh | CEA CO2 Baseline Database v20.0 Table S-1, FY 2022-23 |
| LPG | `lpg_stationary_ipcc_2006` | 2.98463 | kgCO2/kg | IPCC 2006 Vol 2 Ch 1 Table 1.2 + Ch 2 Table 2.5 |

Petrol and diesel (both `status: unresolved`, `value: null`) are excluded from targets and from intermediate generation.

---

## 3. Schema v1 — Field Definitions

> Tags: `[repo]` = value documented in the repository; `[assumption]` = design decision requiring empirical calibration.

### 3.1 Record Metadata (5 fields)

> Metadata fields are stored in every row of the dataset file.
> Fields marked **run-level** have the same value for all records in a single generation run;
> they are stored per-row to make each record self-describing and to allow future runs to be
> concatenated without ambiguity. Fields marked **record-level** are unique per row.

| Field | Scope | Type | Values / Range | Tag |
|---|---|---|---|---|
| `record_id` | record-level | `str` (UUID v4) | unique per record | `[assumption]` |
| `schema_version` | run-level | `str` | `"v1"` | `[assumption]` |
| `generation_run_id` | run-level | `str` (UUID v4) | unique per generation run | `[assumption]` |
| `random_seed` | run-level | `int` | configurable; default 42 | `[assumption]` |
| `is_synthetic` | run-level | `bool` | always `True` for generated data | `[assumption]` |

### 3.2 Household Descriptors (5 fields)

| Field | Type | Values / Range | Tag |
|---|---|---|---|
| `household_size` | `int` | 1–10 | `[assumption]` |
| `dwelling_type` | enum | `apartment` \| `independent_house` \| `chawl_shared` | `[assumption]` |
| `settlement_type` | enum | `urban` \| `peri_urban` \| `rural` | `[assumption]` |
| `state` | enum | ISO 3166-2:IN codes — see Section 6, U1 (resolved for v1) | `[assumption]` |
| `monthly_household_income_band` | enum | `<10k` \| `10k-25k` \| `25k-50k` \| `50k-100k` \| `>100k` (INR/month) | `[assumption]` |

### 3.3 Lifestyle / Occupancy Descriptors (5 fields)

| Field | Type | Values / Range | Tag |
|---|---|---|---|
| `daytime_occupancy_hours` | `float` | 0.0–24.0 | `[assumption]` |
| `cooking_fuel_primary` | enum | `lpg` \| `electricity` \| `biomass` \| `piped_gas` \| `none` | `[assumption]` |
| `cooking_fuel_secondary` | enum | `lpg` \| `electricity` \| `biomass` \| `none` | `[assumption]` |
| `num_working_members` | `int` | 0 – min(`household_size`, 6) — see §5.1 | `[assumption]` |
| `climate_zone` | enum | `hot_dry` \| `warm_humid` \| `composite` \| `temperate` \| `cold` | `[assumption]` |

### 3.4 Appliance Ownership — Capability Proxies (4 fields)

> These fields indicate whether an appliance is **owned**, not how much electricity it uses.
> Usage hours are derived probabilistically from these during intermediate generation.

| Field | Type | Values | Tag |
|---|---|---|---|
| `has_air_conditioner` | `bool` | True / False | `[assumption]` |
| `has_refrigerator` | `bool` | True / False | `[assumption]` |
| `has_washing_machine` | `bool` | True / False | `[assumption]` |
| `has_personal_vehicle` | `bool` | True / False | `[assumption]` |

> `has_personal_vehicle`: future transport scope only; not used in Stage B targets.

### 3.5 Generated Activity Quantities (2 fields — stored; C3.3 targets, not model inputs)

> **Must be excluded from the feature matrix X before any model training.** For C3.3,
> these quantities are the target variables y. They are stored for reproducibility and audit,
> and are the bridge between descriptors and deterministically derived emissions.

| Field | Type | Unit | Tag |
|---|---|---|---|
| `electricity_kwh_per_month` | `float` | kWh | `[assumption]` |
| `lpg_kg_per_month` | `float` | kg | `[assumption]` |

### 3.6 Derived Calculator Outputs (3 fields — not C3.3 ML labels)

> Computed deterministically by `CarbonCalculatorService.calculate()` from the activity
> quantities. These schema fields are not independent observations or labels for the C3.3
> descriptor-only consumption experiment. The calculator is not modified by this design.

| Field | Type | Unit | Calculator source |
|---|---|---|---|
| `total_emissions_kg_co2` | `float` | kgCO2/month | `[repo]` `CalculationResponse.total_emissions_kg_co2` |
| `direct_emissions_kg_co2` | `float` | kgCO2/month | `[repo]` `CalculationResponse.direct_emissions_kg_co2` |
| `indirect_emissions_kg_co2` | `float` | kgCO2/month | `[repo]` `CalculationResponse.indirect_emissions_kg_co2` |

---

## 4. Field Count Summary

| Group | Count | Role |
|---|---|---|
| Metadata | 5 | Identifier / run provenance |
| Household descriptors | 5 | X |
| Lifestyle / occupancy | 5 | X |
| Appliance ownership | 4 | X |
| **Total model inputs (X)** | **14** | |
| Generated intermediates | 2 | Stored, not X |
| Derived calculator outputs | 3 | Calculated from activity quantities; not C3.3 y |
| **Total fields in dataset file** | **24** | |

> `MODEL_INPUT_FIELDS` (14 fields) excludes all 5 metadata fields, both activity quantities, and all 3 derived calculator outputs.
> The 5 metadata fields are never passed to a model.

---

## 5. Generation Decisions (Stage C1.1)

### 5.1 Consistency Constraints (schema-implied; enforced before intermediate generation)

| # | Constraint | Rule | Basis |
|---|---|---|---|
| C1 | Working members ≤ household size | `num_working_members` is drawn from `[0, min(household_size, 6)]` | Schema implies a household cannot have more working members than residents |
| C2 | `num_working_members` upper cap | Hard cap at 6 regardless of household size | `[assumption]` — undocumented; flagged as unresolved in C1 review |
| C3 | `cooking_fuel_secondary ≠ cooking_fuel_primary` | Secondary fuel must differ from primary unless primary is `none` (see C6) | Logical: a secondary fuel is a different fuel; `[assumption]` |
| C4 | `cooking_fuel_secondary` allowed to be `none` | `none` is always a valid secondary value | Captures single-fuel and no-cooking households |
| C5 | State/climate-zone mapping | **Unresolved** — no state→climate_zone mapping exists in the repo; `state` and `climate_zone` are drawn independently in v1 | See §6 |
| C6 | `cooking_fuel_primary = none` with `cooking_fuel_secondary = lpg` | **Valid and permitted.** `none` means the household has no identifiable primary cooking fuel (e.g., communal kitchen, eating out, irregular cooking). A secondary LPG fuel is meaningful in this context (occasional use). `lpg_kg_per_month` is drawn from the secondary distribution. | `[assumption]` |

### 5.2 Grid Access Assumption (Decision 3)

**All v1 records assume grid electricity access.**

- `electricity_kwh_per_month` is always generated as a positive float (see §5.4).
- No field encodes grid connectivity; off-grid or rural electricity-absent households are **not modelled in v1**.
- `electricity_kwh_per_month` is never `None` in v1; the calculator will always return `calculation_status: complete_for_provided_inputs` for electricity.

**Interpretation limit this creates:** The dataset over-represents electrified households. Any model trained on it will not generalise to off-grid populations. This must be stated in the model card.

### 5.3 LPG Generation Rules (Decision 2)

LPG intermediate generation is fully determined by `cooking_fuel_primary` and `cooking_fuel_secondary`. **v1 generates no missing values for `lpg_kg_per_month`.**

**`cooking_fuel_primary = none` defined:** A value of `none` indicates the household has no identifiable primary cooking fuel — for example, a household that relies on communal cooking, eats out predominantly, or cooks only occasionally and cannot be assigned a dominant fuel type. It does not mean cooking is impossible; it means no primary fuel is attributable.

| `cooking_fuel_primary` | `cooking_fuel_secondary` | `lpg_kg_per_month` | Label |
|---|---|---|---|
| `lpg` | any (≠ `lpg` per C3) | drawn from primary distribution (§5.4) | **primary LPG** |
| `electricity` / `biomass` / `piped_gas` | `lpg` | drawn from secondary distribution (§5.4, lower scale) | **secondary LPG** |
| `none` | `lpg` | drawn from secondary distribution (§5.4, lower scale) | **secondary LPG** (permitted — see C6) |
| `electricity` / `biomass` / `piped_gas` / `none` | `biomass` / `electricity` / `none` | `0.0` (explicit zero by construction) | **no LPG** |

**`none` primary + `lpg` secondary — validity decision (C6):** This combination is **valid and permitted in v1**. The rationale is that a household with no dominant primary fuel may still use LPG occasionally (secondary use). Generating `lpg_kg_per_month` from the secondary distribution (lower scale) is consistent with that interpretation. This is `[assumption]` — no survey evidence is cited.

**Distinction between explicit zero and missing:** An explicit `0.0` is passed to the calculator for no-LPG households. `lpg_kg_per_month` is never `None` in v1. The calculator returns `status: calculated`, `emissions_kg_co2 = 0.0`, `activity_amount = 0.0` for zero-LPG rows. A `None` would produce `status: not_provided`; that does not occur in this dataset.

**Assumption on "secondary" LPG scale:** Secondary LPG users are assumed to consume less than primary users. The scale parameter of the secondary distribution is lower (see §5.4). This is `[assumption (requires empirical calibration)]`.

### 5.4 Intermediate Generation Distributions (Decision 1)

> All parameters below are `[assumption (requires empirical calibration)]` unless marked `[repo]`.
> All values are configurable via the generation script's config object.
> A global seed (default 42, §5.5) makes all draws reproducible.
>
> **Truncation requirement:** Both distributions use genuine truncation (rejection sampling or
> scipy `truncnorm`/`truncated` equivalent). Silent clipping — drawing from an untruncated
> distribution and then clamping the result — is **not permitted**, as it distorts the
> distribution shape near the bounds and must not be substituted for truncation in the
> Stage C2 implementation.

#### Electricity: `electricity_kwh_per_month`

Distribution family: **Truncated LogNormal** (lower bound = 10 kWh, upper bound = 2000 kWh).
LogNormal is chosen because electricity consumption is strictly positive, right-skewed, and bounded away from zero for any electrified household.

| Parameter | Symbol | Default value | Depends on | Rationale |
|---|---|---|---|---|
| Log-mean (μ) | `mu` | 5.0 (≈ 148 kWh at median) | — | Base level for a median urban household; `[assumption]` |
| Log-std (σ) | `sigma` | 0.6 | — | Moderate spread; `[assumption]` |
| AC multiplier | `m_ac` | 1.8 | `has_air_conditioner = True` | AC is a dominant load; multiplied on the pre-log scale; `[assumption]` |
| Refrigerator multiplier | `m_ref` | 1.15 | `has_refrigerator = True` | Near-constant baseload; `[assumption]` |
| Washing machine multiplier | `m_wm` | 1.10 | `has_washing_machine = True` | Intermittent load; `[assumption]` |
| Household size multiplier | `m_hs` | 1.0 + 0.05 × (`household_size` − 1) | `household_size` | Larger household uses more electricity; linear approximation; `[assumption]` |
| Climate zone multiplier | `m_cz` | hot_dry=1.3, warm_humid=1.2, composite=1.0, temperate=0.9, cold=0.85 | `climate_zone` | Hot zones drive AC and cooling load; `[assumption]` |
| Occupancy multiplier | `m_occ` | 1.0 + 0.02 × `daytime_occupancy_hours` | `daytime_occupancy_hours` | More hours at home → more daytime consumption; `[assumption]` |
| Settlement type scalar | `s_st` | urban=1.0, peri_urban=0.85, rural=0.70 | `settlement_type` | Rural electrified households tend to consume less; `[assumption]` |

**Combined draw procedure (pseudocode):**
```
scale = mu + ln(m_ac) + ln(m_ref) + ln(m_wm) + ln(m_hs) + ln(m_cz) + ln(m_occ) + ln(s_st)
raw  = TruncatedLogNormal(mu=scale, sigma=sigma, low=10, high=2000)
electricity_kwh_per_month = raw
```

#### LPG: `lpg_kg_per_month`

Distribution family: **Truncated LogNormal** (lower bound = 0.5 kg, upper bound = 60 kg) for households that use LPG; `0.0` (deterministic) for no-LPG households.

| Parameter | Symbol | Default value | Depends on | Rationale |
|---|---|---|---|---|
| Log-mean primary (μ_p) | `mu_primary` | 2.7 (≈ 14.9 kg at median) | `cooking_fuel_primary = lpg` | Roughly 1.5 cylinders of 10 kg; `[assumption]` |
| Log-mean secondary (μ_s) | `mu_secondary` | 1.6 (≈ 5.0 kg at median) | `cooking_fuel_secondary = lpg` | Secondary/backup use is lower; `[assumption]` |
| Log-std (σ) | `sigma` | 0.5 | — | Moderate spread for both tiers; `[assumption]` |
| Household size multiplier | `m_hs` | 1.0 + 0.08 × (`household_size` − 1) | `household_size` | More people cook more; `[assumption]` |
| Lower bound | — | 0.5 kg | — | Avoids degenerate near-zero draws for LPG users; `[assumption]` |
| Upper bound | — | 60 kg | — | Six 10-kg cylinders per month; extreme upper cap; `[assumption]` |

**Combined draw procedure (pseudocode):**
```
# Primary LPG household
scale = mu_primary + ln(m_hs)
lpg_kg_per_month = TruncatedLogNormal(mu=scale, sigma=sigma, low=0.5, high=60)

# Secondary LPG household
scale = mu_secondary + ln(m_hs)
lpg_kg_per_month = TruncatedLogNormal(mu=scale, sigma=sigma, low=0.5, high=60)

# No-LPG household
lpg_kg_per_month = 0.0  # explicit zero by construction
```

### 5.5 Dataset Configuration (Decision 4)

| Parameter | Default | Notes |
|---|---|---|
| `N_RECORDS` | 10 000 | Development choice; not a statistically justified sample size. Configurable. |
| `RANDOM_SEED` | 42 | Reproduces sampled descriptors, activity values, and calculator targets with the same seed, configuration, and compatible execution environment. Random UUID metadata varies between runs, so byte-for-byte CSV reproducibility is not guaranteed. Stored per record as `random_seed` (§3.1). |
| `SCHEMA_VERSION` | `"v1"` | Stored per record as `schema_version` (§3.1); allows future schema versions to coexist in the same file after concatenation. |

These are **development defaults**, not claims about minimum sample size or statistical power.

### 5.6 Target Precision Policy (Decision 5)

**Authoritative source:** The existing `CarbonCalculatorService` is the sole source of target values and is not modified by this dataset design. Targets are extracted directly from the `CalculationResponse` object returned by the calculator.

The calculator applies `round(x, 4)` to each target field before returning the response (see `calculator.py` lines 250–252). Stored targets therefore preserve the calculator's four-decimal-rounded values, not unrounded intermediates. There is no separate full-precision storage stage: the targets stored in the dataset file are the values returned by the calculator.

| Context | Precision |
|---|---|
| **Dataset file storage** | Four decimal places — the values as returned by `CalculationResponse` |
| **API responses** | Same four-decimal values from the calculator — **not changed** |
| **CSV / Parquet exports** | Values written as-is from storage; no additional rounding step |

**Known artefact:** The calculator accumulates `raw_direct` and `raw_indirect` at full float precision internally, then rounds each independently and rounds their sum separately. Therefore:
```
CalculationResponse.direct_emissions_kg_co2   # round(raw_direct, 4)
+ CalculationResponse.indirect_emissions_kg_co2  # round(raw_indirect, 4)
≠ CalculationResponse.total_emissions_kg_co2   # round(raw_direct + raw_indirect, 4)
# possible discrepancy of ±0.0001
```
This is a known, expected artefact of the existing calculator. It must be stated in any model card or dataset description that uses all three target columns. The calculator is not changed.

---

## 6. Unresolved Issues (carry forward to Stage C2)

| # | Issue | Status |
|---|---|---|
| U1 | **State/UT canonical enum list** | **Resolved for the v1 implementation:** the schema validates and generator samples the current 36 ISO 3166-2:IN subdivision codes, including `IN-JK`, `IN-LA`, and merged `IN-DH`. See the [ISO Online Browsing Platform](https://www.iso.org/obp/ui/#iso:code:3166:IN). |
| U2 | **State → climate-zone mapping** | No mapping exists in the repo. ECBC 2017 zone map was cited as design intent but is not linked or verified. State and climate zone are drawn independently in v1. A validated mapping must be added before claiming geographic realism. **Unresolved.** |
| U3 | **`num_working_members` cap at 6** | Cap is `[assumption]`; households of size 7–10 may plausibly have more than 6 working members. No data source cited. **Unresolved.** |
| U4 | **`cooking_fuel_secondary` class imbalance** | Majority of records will have `none`. Whether this field carries sufficient signal to justify inclusion is an empirical question. **Unresolved; keep field in v1.** |
| U5 | **All distribution parameters** | Every numeric parameter in §5.4 is `[assumption (requires empirical calibration)]`. No Indian consumption survey has been cited or used. **Unresolved.** |
| U6 | **Joint occupancy/working-member constraint** | No joint distribution or mutual constraint between `daytime_occupancy_hours` and `num_working_members` is specified; records may be internally inconsistent (e.g., all members work but high occupancy hours). **Unresolved; accepted for v1.** |
| U7 | **Petrol/diesel transport intermediates** | Not generated; `has_personal_vehicle` is a future-scope descriptor only. Re-evaluated when volumetric factors are independently verified and added to `factors.yaml`. **Unresolved.** |
| U8 | **State-level grid emission factors** | The calculator uses `DEFAULT_REGION = "India"` (`[repo]` config.py L29) for all records. No state-level CEA factors are verified in the repo. If added later, `electricity_kwh_per_month` targets will need recomputation. **Unresolved; v1 uses national average only.** |

---

## 7. MODEL_INPUT_FIELDS Allowlist (authoritative)

```python
MODEL_INPUT_FIELDS: list[str] = [
    # Household descriptors
    "household_size",
    "dwelling_type",
    "settlement_type",
    "state",
    "monthly_household_income_band",
    # Lifestyle / occupancy
    "daytime_occupancy_hours",
    "cooking_fuel_primary",     # intended signal: determines LPG generation
    "cooking_fuel_secondary",   # intended signal: secondary LPG generation
    "num_working_members",
    "climate_zone",
    # Appliance ownership (capability proxies)
    "has_air_conditioner",
    "has_refrigerator",
    "has_washing_machine",
    "has_personal_vehicle",     # future scope; included for extensibility
]
# Total: 14 fields
```

**Explicitly excluded from X:**

| Category | Fields |
|---|---|
| Activity amounts (intermediates) | `electricity_kwh_per_month`, `lpg_kg_per_month` |
| Targets | `total_emissions_kg_co2`, `direct_emissions_kg_co2`, `indirect_emissions_kg_co2` |
| Record identifier | `record_id` |
| All calculator response fields | `calculation_status`, `total_is_partial`, `factor_*`, `source_*`, `footprint_scope_note`, `assumptions` (not stored in dataset) |

---

## 8. Stage C2 Deliverables (implemented)

| Deliverable | Implemented path |
|---|---|
| Pydantic record schema | `backend/app/schemas/dataset.py` → `SyntheticHouseholdRecord` |
| Generation config and script | `backend/scripts/generate_synthetic_data.py` → `GenerationConfig` and CLI |
| Dataset output | `backend/data/synthetic/household_records_v1.csv` |
| Schema + leakage tests | `backend/tests/test_dataset_schema.py` |

---

## 9. Stage C2.2 Generator Implementation Choices

The generator uses a local NumPy `default_rng` seeded from `RANDOM_SEED`. Continuous and
categorical draws use that same generator. Lognormal truncation uses rejection sampling;
accepted values are never clipped. Descriptor sampling is a design assumption, not a
calibrated population model:

- Categorical descriptor values and Indian subdivisions are sampled uniformly; appliance
  ownership uses equal-probability Boolean draws. Household size and working-member counts
  are sampled uniformly within their documented integer ranges, and daytime occupancy is
  sampled uniformly over `[0, 24]`. These marginal draws are independent except for the
  explicit household-size constraint and cooking-fuel validity rules.
- Primary cooking fuel is sampled uniformly. To make the documented “majority ... `none`”
  secondary-fuel expectation concrete, `cooking_fuel_secondary` defaults to `none` with
  probability `0.70`; the remaining probability is shared uniformly over valid non-`none`
  choices. This configurable weight is an uncalibrated design assumption.
- `record_id` and `generation_run_id` are random UUID v4 values. The seed reproduces sampled
  descriptors, intermediates, and calculator targets, but those UUIDs differ across runs,
  so a repeated run does not produce byte-for-byte identical CSV output.
- Targets are copied from `CarbonCalculatorService.calculate()` without further rounding.
  CSV creation uses a temporary file in the destination directory and replaces the
  destination only after all rows pass schema validation.
