import asyncio
import csv
from pathlib import Path

import config
import main
import pipeline
import run_dir

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini.csv"


async def _fake_infer(purl, lib_name, version, model):
    return {
        "license_name": "MIT",
        "license_code_url": "https://example.com/LICENSE",
        "reasoning": "mocked sources ok",
        "attempts": 1,
    }


def test_mocked_license_lands_in_results_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)

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
        assert row["inferred_license_name"] == "MIT"
        assert row["inferred_license_code_url"] == "https://example.com/LICENSE"
        assert row["inferred_copyright"] == "UNKNOWN"
        slug = row["component_name"]
        story = (out / "per_component" / slug / pipeline.STORY_FILENAME).read_text(
            encoding="utf-8"
        )
        assert "mocked sources ok" in story
        assert "attempts=1" in story
        assert "timing_s=" in story


def test_empty_purl_noted_in_story(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)

    from input_csv import Component

    comp = Component(
        component_name="solo@1.0",
        purl="",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    run = tmp_path / "run"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    result = asyncio.run(pipeline.process_component(comp, run, "claude-haiku-4-5"))
    assert result.inferred_license_name == "MIT"
    story = (run / "per_component" / comp.slug / pipeline.STORY_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "no purl" in story
    assert "mocked sources ok" in story
