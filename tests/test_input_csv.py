import csv
from pathlib import Path

import pytest

import input_csv

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini.csv"


def test_read_mini_fixture():
    comps = input_csv.read_components(FIXTURE)
    assert len(comps) == 3
    assert comps[0].component_name == "awesome.me@1.0.277"
    assert comps[0].lib_name == "awesome.me"
    assert comps[0].version == "1.0.277"
    assert comps[0].purl == "pkg:npm/awesome.me@1.0.277"
    assert comps[0].slug == "awesome.me@1.0.277"
    assert comps[1].purl == ""
    assert comps[1].extras.get("notes") == "empty purl"
    assert list(comps[2].extras) == ["notes"]


def test_missing_columns_exits(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="component_name and purl"):
        input_csv.read_components(path)


def test_duplicate_component_name_exits(tmp_path):
    path = tmp_path / "dup.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["component_name", "purl"])
        w.writeheader()
        w.writerow({"component_name": "a@1", "purl": "pkg:npm/a@1"})
        w.writerow({"component_name": "a@1", "purl": "pkg:npm/a@2"})
    with pytest.raises(SystemExit, match="conflict for component"):
        input_csv.read_components(path)


def test_slug_collision_exits(tmp_path):
    path = tmp_path / "collide.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["component_name", "purl"])
        w.writeheader()
        w.writerow({"component_name": "a/b@1", "purl": "pkg:npm/a@1"})
        w.writerow({"component_name": "a\\b@1", "purl": "pkg:npm/b@1"})
    with pytest.raises(SystemExit, match="slug collision"):
        input_csv.read_components(path)


def test_make_slug_replaces_unsafe():
    assert input_csv.make_slug('a\\b/c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


# ── A / ADR-0011: dedup, conflict, project_names ──────────────────────────────


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_duplicate_identical_rows_deduped(tmp_path):
    """Same name + same purl, no GT cols → one Component; project_names empty."""
    path = tmp_path / "dup.csv"
    _write_csv(path, ["component_name", "purl"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1"},
        {"component_name": "a@1", "purl": "pkg:npm/a@1"},
    ])
    comps = input_csv.read_components(path)
    assert len(comps) == 1
    assert comps[0].component_name == "a@1"
    assert comps[0].project_names == ()


def test_duplicate_differing_purl_exits(tmp_path):
    """Differing purl → SystemExit naming the component."""
    path = tmp_path / "conf.csv"
    _write_csv(path, ["component_name", "purl"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1"},
        {"component_name": "a@1", "purl": "pkg:npm/a@99"},
    ])
    with pytest.raises(SystemExit, match=r"conflict for component.*purl"):
        input_csv.read_components(path)


def test_duplicate_differing_gt_license_name_exits(tmp_path):
    path = tmp_path / "conf.csv"
    _write_csv(path, ["component_name", "purl", "license_name"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "license_name": "MIT"},
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "license_name": "Apache-2.0"},
    ])
    with pytest.raises(SystemExit, match=r"conflict for component.*license_name"):
        input_csv.read_components(path)


def test_duplicate_differing_gt_copyright_exits(tmp_path):
    path = tmp_path / "conf.csv"
    _write_csv(path, ["component_name", "purl", "copyright"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "copyright": "Alice"},
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "copyright": "Bob"},
    ])
    with pytest.raises(SystemExit, match=r"conflict for component.*copyright"):
        input_csv.read_components(path)


def test_duplicate_empty_vs_populated_gt_is_conflict(tmp_path):
    """Empty-vs-populated GT field counts as a conflict (A3)."""
    path = tmp_path / "conf.csv"
    _write_csv(path, ["component_name", "purl", "license_name"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "license_name": ""},
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "license_name": "MIT"},
    ])
    with pytest.raises(SystemExit, match=r"conflict for component"):
        input_csv.read_components(path)


def test_duplicate_whitespace_normalized_not_conflict(tmp_path):
    """`'MIT'` vs `' mit '` on a GT field → NOT a conflict (A3 normalization)."""
    path = tmp_path / "ok.csv"
    _write_csv(path, ["component_name", "purl", "license_name"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "license_name": "MIT"},
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "license_name": " mit "},
    ])
    comps = input_csv.read_components(path)
    assert len(comps) == 1
    # First-occurrence literal wins (A4)
    assert comps[0].extras["license_name"] == "MIT"


def test_duplicate_differing_passthrough_no_error(tmp_path):
    """Differing non-GT passthrough column → no error; first row's literals win."""
    path = tmp_path / "ok.csv"
    _write_csv(path, ["component_name", "purl", "notes"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "notes": "first"},
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "notes": "second"},
    ])
    comps = input_csv.read_components(path)
    assert len(comps) == 1
    assert comps[0].extras["notes"] == "first"


def test_project_names_aggregated(tmp_path):
    """`project_name` column → ordered, first-seen-unique set per component."""
    path = tmp_path / "proj.csv"
    _write_csv(path, ["component_name", "purl", "project_name"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "project_name": "Alpha"},
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "project_name": "Beta"},
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "project_name": "Alpha"},  # dup
        {"component_name": "b@2", "purl": "pkg:npm/b@2", "project_name": "Gamma"},
    ])
    comps = input_csv.read_components(path)
    a = next(c for c in comps if c.component_name == "a@1")
    b = next(c for c in comps if c.component_name == "b@2")
    assert a.project_names == ("Alpha", "Beta")
    assert b.project_names == ("Gamma",)


def test_project_names_blank_cell_included(tmp_path):
    """Blank `project_name` contributes `''` to the tuple."""
    path = tmp_path / "proj.csv"
    _write_csv(path, ["component_name", "purl", "project_name"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "project_name": ""},
        {"component_name": "a@1", "purl": "pkg:npm/a@1", "project_name": "X"},
    ])
    comps = input_csv.read_components(path)
    assert comps[0].project_names == ("", "X")


def test_project_names_absent_column_empty_tuple(tmp_path):
    """No `project_name` column → `project_names` is empty tuple."""
    path = tmp_path / "noproj.csv"
    _write_csv(path, ["component_name", "purl"], [
        {"component_name": "a@1", "purl": "pkg:npm/a@1"},
    ])
    comps = input_csv.read_components(path)
    assert comps[0].project_names == ()
