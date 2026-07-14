import asyncio
import csv
from pathlib import Path
from unittest.mock import AsyncMock

import config
import main
import pipeline
import run_dir
from download import DownloadResult

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini.csv"


async def _fake_infer(purl, lib_name, version, model):
    return {
        "license_name": "MIT",
        "license_code_url": "https://github.com/foo/bar/blob/main/LICENSE",
        "reasoning": "mocked sources ok",
        "attempts": 1,
    }


async def _fake_download(claude_url, purl, dest_dir, slug):
    raw = "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    licenses = dest_dir / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    path = licenses / f"{slug}.txt"
    path.write_bytes(b"MIT License\n")
    per = dest_dir / "per_component" / slug
    per.mkdir(parents=True, exist_ok=True)
    (per / path.name).write_bytes(b"MIT License\n")
    return DownloadResult(
        resolved_url=raw,
        saved_path=path,
        original_url=claude_url,
        attempts=[f"rewrite {claude_url} -> {raw}", f"ok {raw} -> {path.name}"],
    )


async def _fake_copyright(license_text):
    return {
        "copyright": "Copyright (c) 2020 Jane Doe",
        "reasoning": "verbatim notice",
    }


def test_mocked_license_lands_in_results_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "extract_copyright", _fake_copyright)

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
    resolved = "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    for row in rows:
        assert row["inferred_license_name"] == "MIT"
        assert row["inferred_license_code_url"] == resolved
        assert row["inferred_copyright"] == "Copyright (c) 2020 Jane Doe"
        slug = row["component_name"]
        story = (out / "per_component" / slug / pipeline.STORY_FILENAME).read_text(
            encoding="utf-8"
        )
        assert "mocked sources ok" in story
        assert "attempts=1" in story
        assert "timing_s=" in story
        assert "download: chose " + resolved in story
        assert "copyright: verbatim notice" in story
        assert (out / "licenses" / f"{slug}.txt").is_file()


def test_process_records_license_file_path(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "extract_copyright", _fake_copyright)

    from input_csv import Component

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    run = tmp_path / "run"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    result = asyncio.run(pipeline.process_component(comp, run, "claude-haiku-4-5"))
    assert result.inferred_license_code_url == (
        "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    )
    assert result.license_file_path == run / "licenses" / "solo@1.0.txt"
    assert result.license_file_path.is_file()
    assert result.download_attempts
    assert result.original_license_url.endswith("/blob/main/LICENSE")
    assert result.inferred_copyright == "Copyright (c) 2020 Jane Doe"


def test_empty_purl_noted_in_story(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "extract_copyright", _fake_copyright)

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
    assert "download: chose" in story


def test_no_file_copyright_unknown_extractor_not_called(tmp_path, monkeypatch):
    async def fail_download(claude_url, purl, dest_dir, slug):
        return DownloadResult(
            resolved_url="",
            saved_path=None,
            error="all candidates failed",
            original_url=claude_url,
            attempts=["fail https://example.com"],
        )

    extract = AsyncMock(side_effect=AssertionError("extract_copyright must not run"))
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", fail_download)
    monkeypatch.setattr(pipeline, "extract_copyright", extract)

    from input_csv import Component

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    run = tmp_path / "run"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    result = asyncio.run(pipeline.process_component(comp, run, "claude-haiku-4-5"))
    assert result.inferred_copyright == "UNKNOWN"
    assert result.license_file_path is None
    extract.assert_not_awaited()
    story = (run / "per_component" / comp.slug / pipeline.STORY_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "copyright: skipped (no license file)" in story
