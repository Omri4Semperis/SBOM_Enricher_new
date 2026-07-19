import json
from datetime import datetime
from pathlib import Path

import config
import input_csv
import run_dir

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini.csv"


def test_model_short_claude():
    assert run_dir.model_short("claude-opus-4-8") == "ClaudeOpu-4-8"
    assert run_dir.model_short("claude-sonnet-5") == "ClaudeSon-5"
    assert run_dir.model_short("claude-haiku-4-5") == "ClaudeHai-4-5"


def test_results_csv_name():
    assert run_dir.results_csv_name("claude-opus-4-8", 3) == "results_ClaudeOpu-4-8_3.csv"


def test_create_run_dir_layout(tmp_path, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 14, 15, 30, 45)

    monkeypatch.setattr(run_dir, "datetime", FixedDateTime)

    comps = input_csv.read_components(FIXTURE)
    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path / "runs",
        run_name=None,
        model="claude-opus-4-8",
        workers=2,
        cache_read=None,
        cache_write=None,
    )
    out = run_dir.create_run_dir(cfg, comps)
    assert out.name == "20260714_153045_ClaudeOpu-4-8_3"
    assert (out / "input" / "mini.csv").is_file()
    snap = json.loads((out / "input" / "config.json").read_text(encoding="utf-8"))
    assert snap["model"] == "claude-opus-4-8"
    assert snap["workers"] == 2
    assert (out / "licenses").is_dir()
    for comp in comps:
        meta_path = out / "per_component" / comp.slug / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta == {"component_name": comp.component_name, "purl": comp.purl}


def _comp(name: str, *project_names: str) -> input_csv.Component:
    return input_csv.Component(
        component_name=name,
        purl=f"pkg:npm/{name}",
        lib_name=name.split("@")[0],
        version=name.split("@")[-1],
        slug=name,
        project_names=project_names,
    )


def test_project_dir_map_no_projects_empty():
    assert run_dir.build_project_dir_map([_comp("a@1"), _comp("b@1")]) == {}


def test_project_dir_map_blank_is_misc():
    assert run_dir.build_project_dir_map([_comp("a@1", "")]) == {"": "_misc"}


def test_project_dir_map_collision_suffix():
    # Distinct raw names that sanitize to the same slug (`/` → `_`).
    comps = [_comp("a@1", "Foo/Bar", "Foo_Bar")]
    got = run_dir.build_project_dir_map(comps)
    assert got["Foo/Bar"] == "Foo_Bar"
    assert got["Foo_Bar"] == "Foo_Bar(1)"


def test_project_dir_map_same_raw_stable():
    comps = [_comp("a@1", "Alpha"), _comp("b@1", "Alpha", "Beta")]
    got = run_dir.build_project_dir_map(comps)
    assert got == {"Alpha": "Alpha", "Beta": "Beta"}
