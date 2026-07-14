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
    with pytest.raises(SystemExit, match="duplicate component_name"):
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
