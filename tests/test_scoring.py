"""Scoring / score.csv tests."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import scoring


@dataclass
class _Fake:
    inferred_license_name: str = "UNKNOWN"
    inferred_license_code_url: str = "UNKNOWN"
    inferred_copyright: str = "UNKNOWN"
    is_eq_license_name: str = ""
    is_eq_license_code_url: str = ""
    is_eq_copyright: str = ""


def test_grade_item_hmu():
    assert scoring.grade_item("MIT", "TRUE") == "h"
    assert scoring.grade_item("MIT", "FALSE") == "m"
    assert scoring.grade_item("UNKNOWN", "FALSE") == "u"
    assert scoring.grade_item("UNKNOWN", "TRUE") == "u"


def test_mixed_tally(tmp_path):
    results = [
        _Fake(
            inferred_license_name="MIT",
            inferred_license_code_url="https://a",
            inferred_copyright="Copyright (c) A",
            is_eq_license_name="TRUE",
            is_eq_license_code_url="TRUE",
            is_eq_copyright="TRUE",
        ),
        _Fake(
            inferred_license_name="MIT",
            inferred_license_code_url="https://b",
            inferred_copyright="UNKNOWN",
            is_eq_license_name="TRUE",
            is_eq_license_code_url="FALSE",
            is_eq_copyright="FALSE",
        ),
        _Fake(
            inferred_license_name="MIT",
            inferred_license_code_url="https://a",
            inferred_copyright="Copyright (c) A",
            is_eq_license_name="TRUE",
            is_eq_license_code_url="TRUE",
            is_eq_copyright="TRUE",
        ),
    ]
    gt = ["license_name", "license_code_url", "copyright"]
    path = scoring.write_score_csv(tmp_path / "score.csv", results, gt)
    assert path is not None
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == [
        "license_name",
        "license_code_url",
        "copyright",
        "Count",
    ]
    by = {
        (r["license_name"], r["license_code_url"], r["copyright"]): r["Count"]
        for r in rows
    }
    assert by[("h", "h", "h")] == "2"
    assert by[("h", "m", "u")] == "1"
    assert all(int(r["Count"]) > 0 for r in rows)


def test_no_gt_skips_file(tmp_path):
    path = scoring.write_score_csv(tmp_path / "score.csv", [_Fake()], [])
    assert path is None
    assert not (tmp_path / "score.csv").exists()


def test_partial_gt_columns_only(tmp_path):
    results = [
        _Fake(inferred_license_name="MIT", is_eq_license_name="TRUE"),
        _Fake(inferred_license_name="Apache-2.0", is_eq_license_name="FALSE"),
    ]
    path = scoring.write_score_csv(
        tmp_path / "score.csv", results, ["license_name"]
    )
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == ["license_name", "Count"]
    counts = {r["license_name"]: r["Count"] for r in rows}
    assert counts == {"h": "1", "m": "1"}
