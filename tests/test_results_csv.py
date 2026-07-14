"""Audit-aware results.csv fieldnames / row shape."""

from __future__ import annotations

import csv
from pathlib import Path

from input_csv import Component
from pipeline import ComponentResult
from results_csv import ResultsWriter, build_fieldnames, detect_gt_columns


def test_detect_gt_columns():
    assert detect_gt_columns(["notes"]) == []
    assert detect_gt_columns(["license_name", "notes"]) == ["license_name"]
    assert detect_gt_columns(
        ["copyright", "license_code_url", "license_name"]
    ) == ["license_name", "license_code_url", "copyright"]


def test_non_audit_fieldnames():
    assert build_fieldnames([], ["notes"]) == [
        "component_name",
        "purl",
        "inferred_license_name",
        "inferred_license_code_url",
        "inferred_copyright",
        "notes",
    ]


def test_full_audit_triplet_order():
    assert build_fieldnames(
        ["license_name", "license_code_url", "copyright"], ["notes"]
    ) == [
        "component_name",
        "purl",
        "license_name",
        "inferred_license_name",
        "is_eq_license_name",
        "license_code_url",
        "inferred_license_code_url",
        "is_eq_license_code_url",
        "copyright",
        "inferred_copyright",
        "is_eq_copyright",
        "notes",
    ]


def test_partial_gt_collapses_item():
    assert build_fieldnames(["license_name"], []) == [
        "component_name",
        "purl",
        "license_name",
        "inferred_license_name",
        "is_eq_license_name",
        "inferred_license_code_url",
        "inferred_copyright",
    ]


def test_writer_audit_row(tmp_path):
    path = tmp_path / "out.csv"
    extras = {
        "license_name": "MIT",
        "license_code_url": "https://example.com/LICENSE",
        "copyright": "Copyright (c) A",
        "notes": "x",
    }
    comp = Component(
        component_name="pkg@1",
        purl="pkg:npm/pkg@1",
        lib_name="pkg",
        version="1",
        slug="pkg@1",
        extras=extras,
    )
    result = ComponentResult(
        component=comp,
        inferred_license_name="MIT",
        inferred_license_code_url="https://raw.example/LICENSE",
        inferred_copyright="Copyright (c) A",
        is_eq_license_name="TRUE",
        is_eq_license_code_url="FALSE",
        is_eq_copyright="TRUE",
    )
    with ResultsWriter(path, list(extras.keys())) as w:
        w.write_row(result)
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys())[2:5] == [
        "license_name",
        "inferred_license_name",
        "is_eq_license_name",
    ]
    assert rows[0]["is_eq_license_name"] == "TRUE"
    assert rows[0]["is_eq_license_code_url"] == "FALSE"
    assert rows[0]["notes"] == "x"


def test_writer_non_audit_unchanged(tmp_path):
    path = tmp_path / "out.csv"
    comp = Component(
        component_name="pkg@1",
        purl="",
        lib_name="pkg",
        version="1",
        slug="pkg@1",
        extras={"notes": "n"},
    )
    result = ComponentResult(
        component=comp,
        inferred_license_name="MIT",
        inferred_license_code_url="UNKNOWN",
        inferred_copyright="UNKNOWN",
    )
    with ResultsWriter(path, ["notes"]) as w:
        w.write_row(result)
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == [
        "component_name",
        "purl",
        "inferred_license_name",
        "inferred_license_code_url",
        "inferred_copyright",
        "notes",
    ]
    assert "is_eq_license_name" not in rows[0]
