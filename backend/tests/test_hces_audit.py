"""Tests for the aggregate-only HCES export audit."""

import csv
import json
import zipfile

import pytest

from scripts.audit_hces_exports import (
    LAYOUT_FILENAME,
    LEVEL01_COLUMNS,
    LEVEL01_FILENAME,
    LEVEL03_COLUMNS,
    LEVEL03_FILENAME,
    LEVEL08_COLUMNS,
    LEVEL08_FILENAME,
    AuditInputError,
    audit_exports,
    write_report,
)

KEY_FIELDS = [
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
]
LEVEL01_HEADER = list(LEVEL01_COLUMNS)
LEVEL03_HEADER = list(LEVEL03_COLUMNS)
LEVEL08_HEADER = list(LEVEL08_COLUMNS)


def _key(household_no: str) -> dict[str, str]:
    return dict(
        zip(
            KEY_FIELDS,
            [
                "HCES",
                "2022",
                "00001",
                "1",
                "01",
                "001",
                "01",
                "11",
                "01",
                "01",
                "1",
                "0001",
                "01",
                "",
                "1",
                household_no,
            ],
            strict=True,
        )
    )


def _write_csv(path, header, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def _files(tmp_path, *, l1=None, l3=None, l8=None, headers=None):
    headers = headers or {
        "01": LEVEL01_HEADER,
        "03": LEVEL03_HEADER,
        "08": LEVEL08_HEADER,
    }
    one = []
    three = []
    for hh, mult in (("01", "1000"), ("02", "2000")):
        key = _key(hh)
        one.append(
            {
                **key,
                "questionaire_no": "H",
                "level": "01",
                "b1q1pt13": "1",
                "b1q1pt14": "",
                "mult": mult,
            }
        )
        three.append(
            {
                **key,
                "questionaire_no": "H",
                "level": "03",
                "b2q2pt1": "4",
                "b4q4pt17": "1",
                "b4q4pt21": "02",
                "mult": mult,
            }
        )
    eight = []
    for code, q3, q5, source in (
        ("332", "0", "120.5", ""),
        ("338", "", "10.0", "1"),
        ("331", "", "-9", "5"),
    ):
        eight.append(
            {
                **_key("01"),
                "questionaire_no": "C",
                "level": "08",
                "b8pt1q2": code,
                "b8pt1q3": q3,
                "b8pt1q4": "",
                "b8pt1q5": q5,
                "b8pt1q6": "1030" if code == "338" else "1000",
                "b8pt1q7": source,
                "mult": "1000",
            }
        )
    if l1 is not None:
        one = l1
    if l3 is not None:
        three = l3
    if l8 is not None:
        eight = l8
    _write_csv(tmp_path / LEVEL01_FILENAME, headers["01"], one)
    _write_csv(tmp_path / LEVEL03_FILENAME, headers["03"], three)
    _write_csv(tmp_path / LEVEL08_FILENAME, headers["08"], eight)
    with zipfile.ZipFile(tmp_path / LAYOUT_FILENAME, "w") as workbook:
        workbook.writestr("[Content_Types].xml", "<Types/>")
        workbook.writestr("xl/workbook.xml", "<workbook/>")


def test_audit_reports_joins_raw_target_observations_and_no_imputation(tmp_path):
    _files(tmp_path)
    report = audit_exports(tmp_path)

    assert report["levels"]["01"]["rows"] == 2
    assert report["levels"]["03"]["rows"] == 2
    assert report["levels"]["08"]["rows"] == 3
    assert report["joins"]["level01_to_level03"] == {
        "level01_only_households": 0,
        "level03_only_households": 0,
    }
    assert report["joins"]["level01_to_level08"]["level01_without_level08_rows"] == 1
    assert report["levels"]["08"]["item_code_rows"] == {
        "331": 1,
        "332": 1,
        "338": 1,
    }
    target = report["levels"]["08"]["target_item_observations"]
    assert target["332"]["raw_quantity_profiles"]["b8pt1q5"]["minimum"] == 120.5
    assert target["332"]["raw_quantity_profiles"]["b8pt1q5"]["zero"] == 0
    assert target["338"]["raw_quantity_profiles"]["b8pt1q5"]["missing"] == 0
    assert target["338"]["raw_source_code_counts_including_blank"] == {"1": 1}
    assert report["imputation_performed"] is False
    assert report["harmonized_targets_created"] is False
    assert report["survey_weights_applied"] is False
    assert report["model_features_used"] == []


def test_audit_keeps_missing_zero_negative_and_nonfinite_values_distinct(tmp_path):
    _files(tmp_path)
    path = tmp_path / LEVEL08_FILENAME
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    rows[0]["b8pt1q5"] = "0"
    rows[1]["b8pt1q5"] = ""
    rows[2]["b8pt1q5"] = "-9"
    rows[0]["b8pt1q3"] = "NaN"
    _write_csv(path, LEVEL08_HEADER, rows)

    profile = audit_exports(tmp_path)["levels"]["08"]["target_item_observations"]
    electricity = profile["332"]["raw_quantity_profiles"]["b8pt1q5"]
    assert electricity["zero"] == 1
    assert electricity["negative"] == 0
    assert electricity["missing"] == 0
    # The non-target item value is not in the target profile; target code 338 stays missing.
    lpg = profile["338"]["raw_quantity_profiles"]["b8pt1q5"]
    assert lpg["missing"] == 1
    electricity_q3 = profile["332"]["raw_quantity_profiles"]["b8pt1q3"]
    assert electricity_q3["non_finite"] == 1
    assert "No zero-use convention" in audit_exports(tmp_path)["limitations"][0]


def test_duplicate_and_unmatched_records_are_counted_not_silently_joined(tmp_path):
    _files(tmp_path)
    one_path = tmp_path / LEVEL01_FILENAME
    with one_path.open(encoding="utf-8", newline="") as source:
        one_rows = list(csv.DictReader(source))
    _write_csv(one_path, LEVEL01_HEADER, [*one_rows, one_rows[0]])

    eight_path = tmp_path / LEVEL08_FILENAME
    with eight_path.open(encoding="utf-8", newline="") as source:
        eight_rows = list(csv.DictReader(source))
    extra = dict(eight_rows[0])
    extra["b1q1pt12"] = "03"
    _write_csv(eight_path, LEVEL08_HEADER, [*eight_rows, extra])

    report = audit_exports(tmp_path)
    assert report["levels"]["01"]["duplicate_household_keys"] == 1
    assert report["levels"]["08"]["unmatched_rows_vs_level01"] == 1
    assert report["levels"]["08"]["duplicate_household_item_keys"] == 0


def test_duplicate_household_item_key_is_flagged(tmp_path):
    _files(tmp_path)
    path = tmp_path / LEVEL08_FILENAME
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    _write_csv(path, LEVEL08_HEADER, [*rows, rows[0]])
    assert audit_exports(tmp_path)["levels"]["08"]["duplicate_household_item_keys"] == 1


def test_design_fields_are_reported_but_never_used_as_features(tmp_path):
    _files(tmp_path)
    report = audit_exports(tmp_path)
    assert "fsu" in report["survey_design_fields_present"]
    assert "stratum" in report["survey_design_fields_present"]
    assert "mult" in report["survey_design_fields_present"]
    assert report["model_features_used"] == []
    assert report["survey_weights_applied"] is False


def test_audit_and_json_are_reproducible(tmp_path):
    _files(tmp_path)
    first = audit_exports(tmp_path)
    second = audit_exports(tmp_path)
    assert first == second
    output = tmp_path / "outside" / "audit.json"
    write_report(first, output)
    first_bytes = output.read_bytes()
    write_report(second, output)
    assert output.read_bytes() == first_bytes
    assert json.loads(first_bytes) == first


def test_audit_rejects_missing_required_columns_and_invalid_layout(tmp_path):
    _files(tmp_path)
    short_header = [field for field in LEVEL01_HEADER if field != "state"]
    _write_csv(
        tmp_path / LEVEL01_FILENAME,
        short_header,
        [{field: value for field, value in _files_row().items() if field != "state"}],
    )
    with pytest.raises(AuditInputError, match="columns do not match"):
        audit_exports(tmp_path)

    _files(tmp_path)
    (tmp_path / LAYOUT_FILENAME).write_text("not xlsx", encoding="utf-8")
    with pytest.raises(AuditInputError, match="valid XLSX"):
        audit_exports(tmp_path)


def _files_row():
    return {
        **_key("01"),
        "questionaire_no": "H",
        "level": "01",
        "b1q1pt13": "1",
        "b1q1pt14": "",
        "mult": "1000",
    }
