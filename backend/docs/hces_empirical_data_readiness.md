# HCES 2022–23: Empirical Data Readiness and Harmonization Contract

**CARBONWISE C5.3 | Status: full structural audit completed; harmonized empirical targets blocked**

This document records what the supplied HCES exports and official material establish,
what remains unresolved, and the guardrails for any later empirical analysis. HCES records
remain in the user-managed private directory outside the repository. No HCES-derived
household table, model input matrix, imputation, calibration, or model training is part of
this milestone.

The full C5.3.1 audit completed against the four private exports. Its aggregate report is
`D:\CARBONWISE-private-data\HCES-2022-23\hces_readiness_audit.json`; audited row counts and
target observations reconcile with the C5.2 findings below. The JSON remains outside Git.

## 1. Inputs and evidence status

The inspected private directory contains:

- `LEVEL - 01(Section 1 and 1_1).csv`
- `LEVEL - 03.csv`
- `LEVEL - 08 (Section 8_1).csv`
- `Layout_HCES_2022_23_1.xlsx`

The layout workbook maps the Level 01–03–08 fixed-width fields and defines a 38-byte
Common-ID. The CSV exports expand the ID into its component columns; they do not contain a
Common-ID column. The exports are UTF-8 CSVs rather than the original fixed-width files, so
byte-for-byte comparison with the original records was not possible.

The official [HCES 2022–23 questionnaire, Appendix A](https://mospi.gov.in/sites/default/files/publication_reports/HCES-22-23/AppendixA.pdf)
and [NSS Report 591](https://mospi.gov.in/sites/default/files/publication_reports/Report_591_HCES_2022-23New.pdf)
were consulted for item, reference-period, source-code, questionnaire, and survey-design
semantics. The local folder does not contain the unit-level data user rider, a separate
multiplier encoding note, or the state-code mapping workbook. The publicly described
estimation design therefore informs the safeguards below, but does not settle stored
multiplier scaling or resolve missing export records.

### Official definitions and observed export facts

| Topic | Official evidence | Verified export observation | Remaining decision |
|---|---|---|---|
| Electricity | Q8.1 item 332 is “electricity (std. unit)” for the last 30 days. | 258,793 item-332 rows; `b8pt1q5` is present, finite, and positive in every row (range 1–6,012). | “Standard unit” is not equated to kWh in the files available here. Do not convert or feed to a kWh calculator target until that equivalence is confirmed. |
| LPG | Q8.1 item 338 is LPG excluding conveyance. The questionnaire says quantity units are kg unless otherwise specified in the item column; LPG has no different quantity unit. Reference period is the last 30 days. | 195,054 item-338 rows; one row has blank `b8pt1q5`; the other 195,053 values are positive (range 0.1–99.4). | A missing quantity is not recoverable from the value field without further source data. |
| Q8.1 quantity columns | Layout maps `b8pt1q3`/`b8pt1q4` to “consumption out of home produce” quantity/value and `b8pt1q5`/`b8pt1q6` to total quantity/value. The questionnaire states total consumption includes home produce. | The LPG record with missing total quantity has `b8pt1q6 = 1030` and `b8pt1q7 = 1`. Electricity `b8pt1q7` is blank on all 258,793 rows; LPG source codes are 1, 5, 6, and 9. | `b8pt1q5` is the total quantity field. Do not add `b8pt1q3` to it. The CSV item-field labels should be retained verbatim when meaning is not needed. |
| Source codes | Questionnaire defines 1 purchase only, 2 home-grown stock only, 3 purchase and home-grown, 4 free collection, 5 exchange, 6 gifts/charities, and 9 others. For LPG, codes 2, 3, and 4 are disallowed. | LPG source counts: 1=194,735; 5=170; 6=45; 9=104. No observed LPG code violates the `@` restriction. Electricity's source cell is blank in the questionnaire table and all CSV item-332 source values are blank. | Blank electricity source matches the questionnaire's blank source entry; do not treat it as an error or a household-use indicator. |
| Missing/zero | The questionnaire defines the questions and units but does not define the CSV export’s omitted-item or blank-quantity convention. | No zero `b8pt1q5` values occur for items 332 or 338. There is one missing LPG quantity. A blank/absent row remains distinct from a recorded zero. | Do not classify item absence, absent Level 08 households, or blanks as zero. No target use/non-use label can be built from these files. |
| Level 08 coverage | Q8.1 is marked to be canvassed for all selected households. | 261,746 Level 01 and Level 03 households; 261,313 have any Level 08 row. All Level 08 household keys join; 433 Level 01/03 households have no Level 08 row (411 survey code 1/original, 22 code 2/substitute, 0 code 3/casualty). | The missing Level 08 records conflict with the “all selected households” instruction. Cause is unresolved; absence cannot be treated as zero. |
| Multiplier and design | NSS Report 591 Appendix B describes a stratified multi-stage design, state/UT strata, sub-strata, FSUs, second-stage strata, panels, sub-samples, and use of multiplier in estimation formulas. | Level 01 contains FSU, sector, state, region, district, stratum, sub-stratum, panel, sub-sample, FOD sub-region, and `mult`. Multipliers are positive and identical across joined Level 01/03 and Level 08 rows. | Stored `mult` scaling and the exact recommended user implementation are not documented in the supplied layout. Do not calculate weighted summaries until the official data-user instructions or metadata establish the scaling and estimator. |
| Key and joins | Layout identifies the first 38 bytes as Common-ID. | Reconstructed key components give 261,746 unique Level 01 keys and 261,746 unique Level 03 keys, with exact set equality. Level 08 has zero unmatched households, zero duplicate household-item keys, and zero duplicate rows. One row has blank sample-SU component `b1q1pt7`; report it as incomplete-key evidence. | Keep raw components and reconstructed key for audit. Do not silently fill a missing key component. |

The LPG value field is not a replacement quantity: the questionnaire describes its value as
derived from cylinder price and the normal number of days to use a cylinder, scaled to 30
days and rounded to whole rupees. Thus the observed value `1030` cannot be used to infer the
missing LPG quantity.

## 2. Feature mapping against the synthetic 14-field contract

The current authoritative feature allowlist is `MODEL_INPUT_FIELDS` in
`backend/app/schemas/dataset.py`. It is a synthetic contract, not a schema that HCES can
currently satisfy.

| CARBONWISE field | HCES field/evidence | Status and safe handling |
|---|---|---|
| `household_size` | Level 03 `b2q2pt1` | Direct count (observed 1–37). Preserve the HCES household definition; do not impose the synthetic 1–10 range. |
| `dwelling_type` | Level 03 `b4q4pt17` / Q4.17 | Unsupported for the synthetic meaning. HCES asks tenure/status (owned, hired, other), not apartment/independent house/chawl structure. Do not relabel. |
| `settlement_type` | Level 01 `sector` | Direct rural/urban code only. There is no peri-urban class. Preserve original code; no forced three-class mapping. |
| `state` | Level 01 `state` | Raw state code exists. ISO 3166-2 mapping workbook is not supplied; retain the code and do not guess the conversion. |
| `monthly_household_income_band` | No household income field in supplied levels | Unavailable. Expenditure is not income and must not be substituted. |
| `daytime_occupancy_hours` | None | Unavailable; do not infer occupancy from employment or household descriptors. |
| `cooking_fuel_primary` | Level 03 `b4q4pt21` / Q4.21 | Raw primary-fuel code is available. LPG=02 and electricity=11; other codes do not map one-to-one to the synthetic classes. Keep raw code; any grouping is a separate, documented approximation. |
| `cooking_fuel_secondary` | None in supplied levels | Unavailable. Do not infer secondary fuel from item consumption or source. |
| `num_working_members` | No employed-member count in supplied Level 03 fields | Unavailable. Household-level income/activity codes do not provide a count of working members. |
| `climate_zone` | None | Unavailable; do not derive from state or settlement. |
| `has_air_conditioner` | Not in supplied levels | Unavailable from these files. Asset/ownership records would need a verified source and field. |
| `has_refrigerator` | Not in supplied levels | Unavailable from these files. Do not treat purchases/expenditure as ownership. |
| `has_washing_machine` | Not in supplied levels | Unavailable from these files. Do not treat purchases/expenditure as ownership. |
| `has_personal_vehicle` | Not in supplied levels | Unavailable from these files. Do not treat purchases/expenditure as ownership. |

**Result:** full 14-feature compatibility is **blocked**. A future study may define a smaller
empirical feature set using HCES-native labels, but that is a separate experiment contract
and must not pretend to conform to the synthetic schema.

## 3. Inclusion, exclusion, and harmonization contract

Until the outstanding definitions are obtained, the only permitted output is an aggregate
structural audit. The included audit program does not produce household rows, target labels,
or features.

If a later version is authorized after the blockers are resolved:

1. Build household keys from the 38-byte Common-ID fields in the official layout. Require
   uniqueness in Levels 01/03 and one row per household-item in Level 08. Quarantine
   incomplete keys, duplicate keys, and unmatched child rows with explicit counts/reasons.
2. Preserve Level 08 `b8pt1q5` as the total-quantity field. Do not derive it from values or
   add `b8pt1q3` to it.
3. Keep item absence, household absence from Level 08, blank quantity, recorded zero,
   non-finite value, negative value, and invalid code as distinct states. Never impute or
   turn absence into zero without an official convention.
4. Treat the one blank LPG quantity as missing. Do not infer it from `b8pt1q6`, source code,
   or an average. Do not create a non-use class from the 66,259 Level 08 households lacking
   item 338 or the 433 households lacking all Level 08 rows.
5. Confirm electricity standard-unit-to-kWh equivalence and multiplier scaling before
   building electricity target values, applying the emissions calculator, or calculating
   population estimates.
6. Keep survey weights, FSU/cluster IDs, strata, sub-strata, panels, sub-samples, and
   household identifiers outside all model features. Use survey-aware estimation and
   uncertainty methods. FSU-grouped splitting is a provisional safeguard pending survey
   design review; a single HCES round cannot by itself provide independent external
   validation.
7. Preserve raw HCES code categories. Do not map HCES values into synthetic categories
   where meanings differ or support is absent. No income proxy, occupancy estimate,
   secondary fuel, or appliance ownership may be manufactured.
8. Use no preprocessing fit on held-out records. Any later household-level evaluation must
   split by the documented sampling clusters/households and report the eligible and
   excluded counts without leakage.

No household-level target is declared eligible by this contract. The positive recorded
item quantities are descriptive observations only until coverage, unit, and missingness
semantics are settled.

## 4. Safe audit implementation

`backend/scripts/audit_hces_exports.py` performs a deterministic, read-only structural
audit with the Python standard library. It checks exact export columns and order, row widths,
reconstructed keys, duplicates, joins, multiplier consistency, raw quantity
missing/zero/negative/non-finite counts, and source-code frequencies. It writes a temporary
SQLite index of household-key/item pairs inside the private input directory, then removes it
automatically. The aggregate JSON includes source filenames and byte sizes, but no hashes,
household keys, or row-level records. It explicitly records that weights were not applied,
imputation was not performed, and harmonized targets were not created.

Run from `backend/`:

```powershell
python -m scripts.audit_hces_exports --input-dir "D:\CARBONWISE-private-data\HCES-2022-23"
```

By default it writes only an aggregate JSON report to
`<input-dir>\hces_readiness_audit.json`. Use `--output` to choose a different private path.
The report contains aggregate counts and profiles only. Keep both source files and report
outside the Git repository. Do not use this report as an analysis dataset.

## 5. Decisions and blockers

| Decision | Status | Basis |
|---|---|---|
| A. Descriptive analysis and weighted population summaries | **Conditional** | Raw file counts and distributions can be described. Weighted population estimates are blocked pending stored multiplier scaling/instructions and resolution of the 433 missing Level 08 households. |
| B. Calibration of synthetic activity distributions | **Blocked** | Electricity standard unit to kWh is unverified; both targets have unresolved item-absence semantics; LPG has one missing total quantity; multiplier use is not confirmed. |
| C. Household-level prediction using HCES | **Blocked** | No complete zero/non-use labels, full 14-feature mapping is unsupported, and design-aware inclusion/splitting is not finalized. |
| D. Independent external validation | **Blocked** | No compatible fully observed target/feature table or independent validation source is available. HCES cannot be used as external validation before a defensible target contract exists. |
| E. Emissions from the existing calculator | **Blocked for a complete HCES target** | Electricity kWh equivalence is unconfirmed and target coverage is incomplete. LPG quantities are in kg by questionnaire convention, but row eligibility and missingness remain unresolved. Existing calculator behavior remains unchanged. |

### Required next evidence

- The official unit-level data user rider / machine-readable metadata describing multiplier
  storage scale, omitted-item behavior, blank/special-value conventions, and export rules.
- An authoritative definition that HCES electricity “standard unit” equals the kWh input
  required by CARBONWISE, or an official conversion instruction.
- Explanation or corrected authorized export for the 433 Level 01/03 households with no
  Level 08 rows and confirmation of the missing LPG quantity record.
- State-code mapping workbook if an ISO subdivision mapping is required.

Until these are supplied and reconciled, the next permitted phase is **C5.4: resolve the
listed semantics and approve the inclusion contract**. Do not construct a harmonized
household dataset, run calibration, train a model, or claim external validation.
