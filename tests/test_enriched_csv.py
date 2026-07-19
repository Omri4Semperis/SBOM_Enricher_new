"""Unit tests for library_approvals_enriched.csv writer."""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import enriched_csv


def _result(name, license_name="MIT", url="https://ex/L", copyright="c", error=""):
    return SimpleNamespace(
        component=SimpleNamespace(component_name=name),
        inferred_license_name=license_name,
        inferred_license_code_url=url,
        inferred_copyright=copyright,
        error=error,
    )


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def test_present_column_overwritten_with_good_value(tmp_path):
    fieldnames = ["component_name", "purl", "license_name"]
    rows = [{"component_name": "a@1", "purl": "p", "license_name": "OLD"}]
    results = [_result("a@1", license_name="MIT")]
    out = tmp_path / "enriched.csv"
    enriched_csv.write_enriched_csv(out, fieldnames, rows, results)
    hdr, data = _read(out)
    assert data[0]["license_name"] == "MIT"
    assert "license_code_url" in hdr and "copyright" in hdr


def test_present_kept_when_ours_empty(tmp_path):
    fieldnames = ["component_name", "license_name"]
    rows = [{"component_name": "a@1", "license_name": "KEEP"}]
    results = [_result("a@1", license_name="  ")]
    out = tmp_path / "e.csv"
    enriched_csv.write_enriched_csv(out, fieldnames, rows, results)
    _, data = _read(out)
    assert data[0]["license_name"] == "KEEP"


def test_present_kept_when_ours_unknown(tmp_path):
    fieldnames = ["component_name", "license_name"]
    rows = [{"component_name": "a@1", "license_name": "KEEP"}]
    results = [_result("a@1", license_name="UNKNOWN")]
    out = tmp_path / "e.csv"
    enriched_csv.write_enriched_csv(out, fieldnames, rows, results)
    _, data = _read(out)
    assert data[0]["license_name"] == "KEEP"


def test_present_kept_when_errored(tmp_path):
    fieldnames = ["component_name", "license_name"]
    rows = [{"component_name": "a@1", "license_name": "KEEP"}]
    results = [_result("a@1", license_name="MIT", error="boom")]
    out = tmp_path / "e.csv"
    enriched_csv.write_enriched_csv(out, fieldnames, rows, results)
    _, data = _read(out)
    assert data[0]["license_name"] == "KEEP"


def test_absent_column_appended_verbatim_including_unknown(tmp_path):
    fieldnames = ["component_name", "purl"]
    rows = [{"component_name": "a@1", "purl": "p"}]
    results = [_result("a@1", license_name="UNKNOWN", url="", copyright="UNKNOWN")]
    out = tmp_path / "e.csv"
    enriched_csv.write_enriched_csv(out, fieldnames, rows, results)
    hdr, data = _read(out)
    assert hdr == ["component_name", "purl", "license_name", "license_code_url", "copyright"]
    assert data[0]["license_name"] == "UNKNOWN"
    assert data[0]["license_code_url"] == ""
    assert data[0]["copyright"] == "UNKNOWN"


def test_duplicate_rows_repeated_with_own_passthrough(tmp_path):
    fieldnames = ["component_name", "project_name", "notes"]
    rows = [
        {"component_name": "a@1", "project_name": "P1", "notes": "one"},
        {"component_name": "a@1", "project_name": "P2", "notes": "two"},
    ]
    results = [_result("a@1", license_name="MIT")]
    out = tmp_path / "e.csv"
    enriched_csv.write_enriched_csv(out, fieldnames, rows, results)
    _, data = _read(out)
    assert len(data) == 2
    assert data[0]["project_name"] == "P1" and data[0]["notes"] == "one"
    assert data[1]["project_name"] == "P2" and data[1]["notes"] == "two"
    assert data[0]["license_name"] == data[1]["license_name"] == "MIT"


def test_column_order_present_in_place_absent_appended(tmp_path):
    fieldnames = ["component_name", "copyright", "purl", "license_name"]
    rows = [
        {
            "component_name": "a@1",
            "copyright": "old-c",
            "purl": "p",
            "license_name": "old-l",
        }
    ]
    results = [_result("a@1", license_name="MIT", url="https://u", copyright="new-c")]
    out = tmp_path / "e.csv"
    enriched_csv.write_enriched_csv(out, fieldnames, rows, results)
    hdr, data = _read(out)
    assert hdr == [
        "component_name",
        "copyright",
        "purl",
        "license_name",
        "license_code_url",
    ]
    assert data[0]["license_name"] == "MIT"
    assert data[0]["copyright"] == "new-c"
    assert data[0]["license_code_url"] == "https://u"


def test_missing_result_raises(tmp_path):
    fieldnames = ["component_name"]
    rows = [{"component_name": "missing@1"}]
    out = tmp_path / "e.csv"
    try:
        enriched_csv.write_enriched_csv(out, fieldnames, rows, [])
        assert False, "expected KeyError"
    except KeyError:
        pass
