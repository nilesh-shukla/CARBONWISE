"""Read-only structural audit for authorized HCES 2022-23 CSV exports.

This tool reports aggregate observations only. It does not harmonize targets,
impute missing values, calculate survey estimates, or write household records.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

LEVEL01_FILENAME = "LEVEL - 01(Section 1 and 1_1).csv"
LEVEL03_FILENAME = "LEVEL - 03.csv"
LEVEL08_FILENAME = "LEVEL - 08 (Section 8_1).csv"
LAYOUT_FILENAME = "Layout_HCES_2022_23_1.xlsx"

LEVEL01_COLUMNS = (
    "survey_name",
    "year",
    "fsu",
    "sector",
    "state",
    "nss_region",
    "district",
    "stratum",
    "sub_stratum",
    "panel",
    "sub_sample",
    "fod_subregion",
    "b1q1pt7",
    "b1q1pt10",
    "b1q1pt11",
    "b1q1pt12",
    "questionaire_no",
    "level",
    "b1q1pt13",
    "b1q1pt14",
    "mult",
)
LEVEL03_COLUMNS = (
    "survey_name",
    "year",
    "fsu",
    "sector",
    "state",
    "nss_region",
    "district",
    "stratum",
    "sub_stratum",
    "panel",
    "sub_sample",
    "fod_subregion",
    "b1q1pt7",
    "b1q1pt10",
    "b1q1pt11",
    "b1q1pt12",
    "questionaire_no",
    "level",
    "b2q2pt1",
    "b4q4pt1",
    "b4q4pt3",
    "b4q4pt5",
    "b4q4pt6",
    "b4q4pt7",
    "b4q4pt8",
    "b4q4pt9",
    "b4q4pt10",
    "b4q4pt11",
    "b4q4pt12",
    "b4q4pt13",
    "b4q4pt14",
    "b4q4pt15",
    "b4q4pt16",
    "b4q4pt17",
    "b4q4pt18",
    "b4q4pt19",
    "b4q4pt20",
    "b4q4pt21",
    "b4q4pt22",
    "b4q4pt23",
    "b4q4pt24",
    "b4q4pt25",
    "b4q4pt26",
    "b4q4pt29",
    "b4q4pt30",
    "b4q4pt31",
    "b4q4pt32",
    "b4q4pt33",
    "mult",
)
LEVEL08_COLUMNS = (
    "survey_name",
    "year",
    "fsu",
    "sector",
    "state",
    "nss_region",
    "district",
    "stratum",
    "sub_stratum",
    "panel",
    "sub_sample",
    "fod_subregion",
    "b1q1pt7",
    "b1q1pt10",
    "b1q1pt11",
    "b1q1pt12",
    "questionaire_no",
    "level",
    "b8pt1q2",
    "b8pt1q3",
    "b8pt1q4",
    "b8pt1q5",
    "b8pt1q6",
    "b8pt1q7",
    "mult",
)

KEY_FIELDS = (
    "survey_name",
    "year",
    "fsu",
    "sector",
    "state",
    "nss_region",
    "district",
    "stratum",
    "sub_stratum",
    "panel",
    "sub_sample",
    "fod_subregion",
    "b1q1pt7",
    "b1q1pt10",
    "b1q1pt11",
    "b1q1pt12",
)
KEY_WIDTHS = (4, 4, 5, 1, 2, 3, 2, 2, 2, 2, 1, 4, 2, 1, 1, 2)
OPTIONAL_BLANK_KEY_FIELDS = {"b1q1pt10"}
SURVEY_DESIGN_FIELDS = (
    "fsu",
    "sector",
    "state",
    "nss_region",
    "district",
    "stratum",
    "sub_stratum",
    "panel",
    "sub_sample",
    "fod_subregion",
    "mult",
)
TARGET_CODES = {"332", "338"}
QUANTITY_FIELDS = ("b8pt1q3", "b8pt1q5")
LEVEL01_PROFILE_FIELDS = (*KEY_FIELDS, "b1q1pt13", "b1q1pt14", "mult")
LEVEL03_PROFILE_FIELDS = (*KEY_FIELDS, "b2q2pt1", "b4q4pt17", "b4q4pt21", "mult")
LEVEL08_PROFILE_FIELDS = (
    *KEY_FIELDS,
    "b8pt1q2",
    "b8pt1q3",
    "b8pt1q4",
    "b8pt1q5",
    "b8pt1q6",
    "b8pt1q7",
    "mult",
)


class AuditInputError(ValueError):
    """Raised when an export cannot be safely audited."""


def _key(record: dict[str, str], level: str, row_number: int) -> tuple[str, int]:
    """Reconstruct layout Common-ID from its expanded CSV components."""
    parts: list[str] = []
    missing_required = 0
    for field, width in zip(KEY_FIELDS, KEY_WIDTHS, strict=True):
        value = (record.get(field) or "").strip()
        if not value:
            if field not in OPTIONAL_BLANK_KEY_FIELDS:
                missing_required += 1
            parts.append(" " * width)
            continue
        if len(value) > width:
            raise AuditInputError(
                f"{level} CSV row {row_number}: {field} exceeds layout width {width}"
            )
        parts.append(value.zfill(width) if value.isdigit() else value.ljust(width))
    return "".join(parts), missing_required


def _key_from_values(
    values: list[str],
    positions: tuple[tuple[int, str, int], ...],
    level: str,
    row_number: int,
) -> tuple[str, int]:
    """Reconstruct the key without allocating a per-row dictionary."""
    parts: list[str] = []
    missing_required = 0
    for position, field, width in positions:
        value = values[position].strip()
        if not value:
            if field not in OPTIONAL_BLANK_KEY_FIELDS:
                missing_required += 1
            parts.append(" " * width)
        elif len(value) > width:
            raise AuditInputError(
                f"{level} CSV row {row_number}: {field} exceeds layout width {width}"
            )
        else:
            parts.append(value.zfill(width) if value.isdigit() else value.ljust(width))
    return "".join(parts), missing_required


def _read_csv(
    path: Path, expected_columns: tuple[str, ...], level: str
) -> tuple[list[str], Any]:
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except (OSError, UnicodeError) as exc:
        raise AuditInputError(f"Cannot open {level} export {path}: {exc}") from exc
    reader = csv.reader(handle)
    try:
        header = next(reader)
    except StopIteration as exc:
        handle.close()
        raise AuditInputError(f"{level} export is empty: {path}") from exc
    if len(set(header)) != len(header):
        handle.close()
        raise AuditInputError(f"{level} export has duplicate column names")
    if tuple(header) != expected_columns:
        handle.close()
        raise AuditInputError(
            f"{level} export columns do not match the verified export layout/order"
        )
    return header, (handle, reader)


def _numeric_profile() -> dict[str, Any]:
    return {
        "rows": 0,
        "missing": 0,
        "invalid": 0,
        "non_finite": 0,
        "zero": 0,
        "negative": 0,
        "minimum": None,
        "maximum": None,
    }


def _add_numeric(profile: dict[str, Any], value: str) -> None:
    value = value.strip()
    if not value:
        profile["missing"] += 1
        return
    try:
        number = float(value)
    except ValueError:
        profile["invalid"] += 1
        return
    if not math.isfinite(number):
        profile["non_finite"] += 1
        return
    profile["rows"] += 1
    profile["zero"] += number == 0
    profile["negative"] += number < 0
    current_min = profile["minimum"]
    current_max = profile["maximum"]
    profile["minimum"] = number if current_min is None else min(current_min, number)
    profile["maximum"] = number if current_max is None else max(current_max, number)


def _scan_level01(
    path: Path,
) -> tuple[dict[str, Any], dict[str, tuple[str, str]], set[str]]:
    header, (handle, reader) = _read_csv(path, LEVEL01_COLUMNS, "Level 01")
    rows = 0
    keys: set[str] = set()
    duplicate_keys: set[str] = set()
    status_by_key: dict[str, str] = {}
    duplicate_household_keys = 0
    duplicate_rows = 0
    missing_fields: Counter[str] = Counter()
    numeric = {"mult": _numeric_profile()}
    malformed = 0
    incomplete_keys = 0
    try:
        for row_number, values in enumerate(reader, start=2):
            rows += 1
            if len(values) != len(header):
                malformed += 1
                continue
            record = dict(zip(header, values, strict=True))
            for field in LEVEL01_PROFILE_FIELDS:
                if record[field] == "":
                    missing_fields[field] += 1
            key, incomplete = _key(record, "Level 01", row_number)
            incomplete_keys += incomplete
            if key in keys:
                if key not in duplicate_keys:
                    duplicate_keys.add(key)
                    duplicate_household_keys += 1
                duplicate_rows += 1
            else:
                keys.add(key)
            status_by_key[key] = (
                record.get("b1q1pt13", "").strip(),
                record["mult"].strip(),
            )
            _add_numeric(numeric["mult"], record["mult"])
    finally:
        handle.close()
    if malformed:
        raise AuditInputError(f"Level 01 export has {malformed} malformed row widths")
    return (
        {
            "rows": rows,
            "columns": len(header),
            "malformed_row_widths": malformed,
            "missing_required_key_components": incomplete_keys,
            "unique_household_keys": len(keys),
            "duplicate_household_keys": duplicate_household_keys,
            "duplicate_rows": duplicate_rows,
            "missing_cells_by_column": dict(sorted(missing_fields.items())),
            "multiplier": numeric["mult"],
        },
        status_by_key,
        keys,
    )


def _scan_level03(path: Path) -> tuple[dict[str, Any], set[str]]:
    header, (handle, reader) = _read_csv(path, LEVEL03_COLUMNS, "Level 03")
    rows = 0
    keys: set[str] = set()
    duplicate_keys: set[str] = set()
    duplicate_household_keys = 0
    duplicate_rows = 0
    missing_fields: Counter[str] = Counter()
    primary_fuels: Counter[str] = Counter()
    numeric = {field: _numeric_profile() for field in ("b2q2pt1", "mult")}
    malformed = 0
    incomplete_keys = 0
    try:
        for row_number, values in enumerate(reader, start=2):
            rows += 1
            if len(values) != len(header):
                malformed += 1
                continue
            record = dict(zip(header, values, strict=True))
            for field in LEVEL03_PROFILE_FIELDS:
                if record[field] == "":
                    missing_fields[field] += 1
            key, incomplete = _key(record, "Level 03", row_number)
            incomplete_keys += incomplete
            if key in keys:
                if key not in duplicate_keys:
                    duplicate_keys.add(key)
                    duplicate_household_keys += 1
                duplicate_rows += 1
            else:
                keys.add(key)
            primary_fuels[record["b4q4pt21"].strip()] += 1
            for field, profile in numeric.items():
                _add_numeric(profile, record[field])
    finally:
        handle.close()
    if malformed:
        raise AuditInputError(f"Level 03 export has {malformed} malformed row widths")
    return (
        {
            "rows": rows,
            "columns": len(header),
            "malformed_row_widths": malformed,
            "missing_required_key_components": incomplete_keys,
            "unique_household_keys": len(keys),
            "duplicate_household_keys": duplicate_household_keys,
            "duplicate_rows": duplicate_rows,
            "missing_cells_by_column": dict(sorted(missing_fields.items())),
            "household_size": numeric["b2q2pt1"],
            "primary_cooking_fuel_codes": dict(sorted(primary_fuels.items())),
        },
        keys,
    )


def _scan_level08(
    path: Path,
    level01_keys: set[str],
    household_metadata: dict[str, tuple[str, str]],
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    header, (handle, reader) = _read_csv(path, LEVEL08_COLUMNS, "Level 08")
    if progress:
        progress("Level 08 CSV header validated")
    column = {name: index for index, name in enumerate(header)}
    key_positions = tuple(
        (column[field], field, width)
        for field, width in zip(KEY_FIELDS, KEY_WIDTHS, strict=True)
    )
    profile_positions = tuple(column[field] for field in LEVEL08_PROFILE_FIELDS)
    rows = 0
    household_keys: set[str] = set()
    duplicate_items = 0
    multiplier_mismatches = 0
    missing_fields: Counter[str] = Counter()
    target_rows: dict[str, int] = Counter()
    target_profiles: dict[str, dict[str, dict[str, Any]]] = {
        code: {field: _numeric_profile() for field in QUANTITY_FIELDS}
        for code in TARGET_CODES
    }
    target_source_codes: dict[str, Counter[str]] = {
        code: Counter() for code in TARGET_CODES
    }
    item_code_rows: Counter[str] = Counter()
    target_q3_gt_q5: Counter[str] = Counter()
    unmatched_rows = 0
    malformed = 0
    incomplete_keys = 0
    temp_dir = tempfile.TemporaryDirectory(prefix=".hces-audit-", dir=path.parent)
    if progress:
        progress("Created temporary audit workspace")
    connection = sqlite3.connect(Path(temp_dir.name) / "household_items.sqlite3")
    connection.execute("PRAGMA journal_mode = OFF")
    connection.execute("PRAGMA synchronous = OFF")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute(
        "CREATE TABLE household_items (item_code TEXT, household_key TEXT)"
    )
    if progress:
        progress("Temporary index table ready")
    batch: list[tuple[str, str]] = []
    try:
        for row_number, values in enumerate(reader, start=2):
            rows += 1
            if progress and rows % 25_000 == 0:
                progress(f"Level 08 scanned {rows:,} rows")
            if len(values) != len(header):
                malformed += 1
                continue
            for field, position in zip(
                LEVEL08_PROFILE_FIELDS, profile_positions, strict=True
            ):
                if values[position] == "":
                    missing_fields[field] += 1
            key, incomplete = _key_from_values(
                values, key_positions, "Level 08", row_number
            )
            incomplete_keys += incomplete
            household_keys.add(key)
            if key not in level01_keys:
                unmatched_rows += 1
            else:
                _, expected_multiplier = household_metadata.get(key, ("", ""))
                if values[column["mult"]].strip() != expected_multiplier:
                    multiplier_mismatches += 1
            code = values[column["b8pt1q2"]].strip()
            item_code_rows[code] += 1
            batch.append((code, key))
            if len(batch) >= 100_000:
                if progress:
                    progress("Writing a 100,000-row temporary index batch")
                connection.executemany(
                    "INSERT INTO household_items VALUES (?, ?)", batch
                )
                batch.clear()
            if code not in TARGET_CODES:
                continue
            target_rows[code] += 1
            target_source_codes[code][values[column["b8pt1q7"]].strip()] += 1
            for field in QUANTITY_FIELDS:
                _add_numeric(target_profiles[code][field], values[column[field]])
            q3 = values[column["b8pt1q3"]].strip()
            q5 = values[column["b8pt1q5"]].strip()
            if q3 and q5:
                try:
                    if float(q3) > float(q5):
                        target_q3_gt_q5[code] += 1
                except ValueError:
                    pass
    finally:
        if batch:
            connection.executemany("INSERT INTO household_items VALUES (?, ?)", batch)
        connection.commit()
        if progress:
            progress("Building temporary item/household index for duplicate check")
        connection.execute(
            "CREATE INDEX household_items_by_item_key "
            "ON household_items(item_code, household_key)"
        )
        unique_households_by_item = Counter(
            dict(
                connection.execute(
                    "SELECT item_code, COUNT(DISTINCT household_key) "
                    "FROM household_items GROUP BY item_code"
                ).fetchall()
            )
        )
        duplicate_items = sum(item_code_rows.values()) - sum(
            unique_households_by_item.values()
        )
        connection.close()
        temp_dir.cleanup()
        handle.close()
    if malformed:
        raise AuditInputError(f"Level 08 export has {malformed} malformed row widths")

    return {
        "rows": rows,
        "columns": len(header),
        "malformed_row_widths": malformed,
        "missing_required_key_components": incomplete_keys,
        "unique_household_keys": len(household_keys),
        "duplicate_household_item_keys": duplicate_items,
        "unmatched_rows_vs_level01": unmatched_rows,
        "multiplier_mismatches_vs_level01": multiplier_mismatches,
        "missing_cells_by_column": dict(sorted(missing_fields.items())),
        "item_code_rows": dict(sorted(item_code_rows.items())),
        "target_item_observations": {
            code: {
                "rows": target_rows[code],
                "distinct_households": unique_households_by_item[code],
                "households_without_item_row_among_level08": max(
                    0, len(household_keys) - unique_households_by_item[code]
                ),
                "raw_quantity_profiles": target_profiles[code],
                "raw_source_code_counts_including_blank": dict(
                    sorted(target_source_codes[code].items())
                ),
                "rows_where_q3_exceeds_q5_when_both_parse": target_q3_gt_q5[code],
                "interpretation": "raw observations only; no zero or eligibility inference",
            }
            for code in sorted(TARGET_CODES)
        },
        "households_without_any_level08_row": len(level01_keys - household_keys),
        "missing_level08_household_survey_codes": dict(
            sorted(
                Counter(
                    household_metadata.get(key, ("", ""))[0]
                    for key in level01_keys - household_keys
                ).items()
            )
        ),
        "household_keys": household_keys,
    }


def audit_exports(
    input_dir: Path, progress: Callable[[str], None] | None = None
) -> dict[str, Any]:
    """Validate exports and return a deterministic aggregate-only report."""
    input_dir = input_dir.expanduser().resolve()
    paths = {
        "level01": input_dir / LEVEL01_FILENAME,
        "level03": input_dir / LEVEL03_FILENAME,
        "level08": input_dir / LEVEL08_FILENAME,
        "layout": input_dir / LAYOUT_FILENAME,
    }
    missing = [path.name for path in paths.values() if not path.is_file()]
    if missing:
        raise AuditInputError(f"Missing required input files in {input_dir}: {missing}")
    if not zipfile.is_zipfile(paths["layout"]):
        raise AuditInputError(
            f"Layout workbook is not a valid XLSX/ZIP file: {paths['layout']}"
        )
    with zipfile.ZipFile(paths["layout"]) as workbook:
        members = set(workbook.namelist())
    if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(members):
        raise AuditInputError(
            f"Layout workbook is missing required XLSX parts: {paths['layout']}"
        )

    if progress:
        progress("Scanning Level 01 identifiers and multipliers")
    level01, household_metadata, level01_keys = _scan_level01(paths["level01"])
    if progress:
        progress("Scanning Level 03 identifiers and household descriptors")
    level03, level03_keys = _scan_level03(paths["level03"])
    level01_only = len(level01_keys - level03_keys)
    level03_only = len(level03_keys - level01_keys)
    del level03_keys
    if progress:
        progress("Scanning Level 08 item observations and joins")
    level08 = _scan_level08(
        paths["level08"], level01_keys, household_metadata, progress
    )

    level08_keys = level08.pop("household_keys")
    report = {
        "audit_version": "1",
        "audit_scope": "aggregate structural audit; no harmonized or model-ready records",
        "input_files": {
            key: {
                "name": path.name,
                "bytes": path.stat().st_size,
            }
            for key, path in sorted(paths.items())
        },
        "encoding_and_layout_checks": {
            "csv_encoding": "utf-8-sig decoder accepted all files",
            "csv_row_widths": "checked against each header during scan",
            "layout_workbook_is_valid_xlsx_container": True,
            "common_id": (
                "reconstructed from 16 expanded CSV components using the layout's "
                "38-byte widths; the CSV exports do not contain a Common-ID column"
            ),
        },
        "levels": {"01": level01, "03": level03, "08": level08},
        "joins": {
            "level01_to_level03": {
                "level01_only_households": level01_only,
                "level03_only_households": level03_only,
            },
            "level01_to_level08": {
                "level08_only_households": len(level08_keys - level01_keys),
                "level01_without_level08_rows": len(level01_keys - level08_keys),
            },
            "key_method": "layout Common-ID reconstructed from fixed-width key components",
        },
        "survey_design_fields_present": list(SURVEY_DESIGN_FIELDS),
        "model_features_used": [],
        "survey_weights_applied": False,
        "imputation_performed": False,
        "harmonized_targets_created": False,
        "target_eligibility": "not determined; missing and absent records remain distinct",
        "limitations": [
            "No zero-use convention is inferred from an absent item or household row.",
            "No stored multiplier scaling or weighted estimate is calculated.",
            "Electricity standard-unit conversion and target eligibility are not applied.",
        ],
    }
    return report


def write_report(report: dict[str, Any], destination: Path) -> None:
    """Write report atomically; never write into the repository by default."""
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - atomic replacement needs a named sibling file.
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    )
    temporary_path = Path(handle.name)
    try:
        with handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing the three CSV exports and official layout workbook",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Aggregate JSON report path (default: <input-dir>/hces_readiness_audit.json)",
    )
    args = parser.parse_args(argv)
    try:
        report = audit_exports(
            args.input_dir,
            progress=lambda message: print(message, file=sys.stderr, flush=True),
        )
        output = args.output or args.input_dir / "hces_readiness_audit.json"
        write_report(report, output)
    except (AuditInputError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Wrote aggregate-only audit report: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
