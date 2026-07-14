import csv
from pathlib import Path

import config
import main
import pipeline
import run_dir

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini.csv"


def test_stub_run_writes_unknown_results(tmp_path):
    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path / "runs",
        run_name=None,
        model="claude-opus-4-8",
        workers=2,
        cache_read=None,
        cache_write=None,
    )
    out = main.run(cfg)
    results_path = out / run_dir.results_csv_name(cfg.model, 3)
    assert results_path.is_file()
    with results_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert list(rows[0].keys())[:5] == [
        "component_name",
        "purl",
        "inferred_license_name",
        "inferred_license_code_url",
        "inferred_copyright",
    ]
    assert "notes" in rows[0]
    for row in rows:
        assert row["inferred_license_name"] == "UNKNOWN"
        assert row["inferred_license_code_url"] == "UNKNOWN"
        assert row["inferred_copyright"] == "UNKNOWN"
        slug = row["component_name"]  # fixture names need no slug rewrite
        story = (out / "per_component" / slug / pipeline.STORY_FILENAME).read_text(
            encoding="utf-8"
        )
        assert "stub: no inference run" in story
