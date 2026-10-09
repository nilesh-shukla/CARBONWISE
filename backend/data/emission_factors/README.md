# Emission Factors Registry & Provenance Audit

This directory contains the traceable emission factors for Phase 2 calculation workflows in the **CARBONWISE** backend.

## Registry Source File
- **[factors.yaml](file:///d:/Projects/CARBONWISE/backend/data/emission_factors/factors.yaml)**: Machine-readable registry storing factors with full citation metadata and validation status.

---

## Provenance Audit Table

| Factor ID | Activity & Fuel | Value | Normalized Unit | Activity Unit | Geography & Period | Boundary | Gas Scope | Status & Provenance |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `electricity_grid_india_cea` | Electricity: Grid | `0.716` | `kgCO2/kWh` | `kWh` | India (FY 2022-23, Version 20.0, Dec 2024) | `indirect_scope_2` | `CO2` | **Verified**: CEA CO2 Baseline Database for the Indian Power Sector, User Guide Version 20.0, Table S-1. Generation busbar weighted average. |
| `lpg_stationary_ipcc_2006` | Cooking/Heating: LPG | `2.98463` | `kgCO2/kg` | `kg` | global_default (2006) | `direct_scope_1` | `CO2` | **Verified**: 2006 IPCC Guidelines Vol 2 (Energy), Ch 1 Tab 1.2 (NCV 47.3 TJ/Gg) & Ch 2 Tab 2.5 (EF 63,100 kg/TJ). Derivation: `0.0000473 TJ/kg * 63,100 kg/TJ = 2.98463 kg/kg`. |
| `petrol_road_ipcc_2006_volumetric` | Transport: Petrol | `null` | `kgCO2/litre` | `litres` | global_default (2006) | `direct_scope_1` | `CO2` | **Unresolved**: IPCC Vol 2 verifies energy/mass defaults (3.07 kg/kg) but provides no default volumetric density (kg/L). Density is not independently verified from an approved national standard. |
| `diesel_road_ipcc_2006_volumetric` | Transport: Diesel | `null` | `kgCO2/litre` | `litres` | global_default (2006) | `direct_scope_1` | `CO2` | **Unresolved**: IPCC Vol 2 verifies energy/mass defaults (3.186 kg/kg) but provides no default volumetric density (kg/L). Density is not independently verified from an approved national standard. |

---

## Strict Provenance & Calculation Policies
1. **Zero Fabrication**: No values may be hardcoded or fabricated in application code.
2. **Missing Input vs. Zero**: An omitted consumption input (`null`) represents "not provided". An explicit `0.0` represents an "explicit zero supplied by the user" (yielding zero emissions for calculable activities).
3. **Status Semantics (`complete_for_provided_inputs` vs `partial`)**:
   - `complete_for_provided_inputs`: Every supplied activity was calculated (`total_is_partial: false`).
   - `partial`: At least one supplied activity could not be calculated due to unresolved factors (`total_is_partial: true`).
   - Omitted activities do not make the result partial and are listed under `not_provided_categories`. Uncalculated categories never enter the total sum.
4. **Scope Disclaimer**: The total emissions sum covers only the supplied, calculable activities and is not a full household footprint.
5. **Global Defaults**: All IPCC 2006 default values retain `geography: global_default` and are never attributed specifically to India.
6. **Boundary Separation**: Scope 1 direct emissions (LPG) and Scope 2 indirect emissions (Grid Electricity) are reported separately.
