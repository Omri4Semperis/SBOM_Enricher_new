import csv
import json
from pathlib import Path

import pytest

import config
import main
import pipeline
import run_dir
from download import DownloadResult
from pricing import UNKNOWN_COST, CallMeta
from summary import build_summary, parse_story_timings

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


async def _fake_copyright(license_text, purl="", lib_name="", version="", model=""):
    return {
        "copyright": "Copyright (c) 2020 Jane Doe",
        "reasoning": "verbatim notice",
    }


def test_parse_story_timings():
    text = (
        "license: ok attempts=1 timing_s=1.250\n"
        "download: chose https://x timing_s=0.500\n"
        "copyright: notice timing_s=0.100\n"
    )
    assert parse_story_timings(text) == {
        "license": 1.25,
        "download": 0.5,
        "copyright": 0.1,
    }


def test_parse_story_reasons():
    from summary import parse_story_reasons

    text = (
        "license: mocked sources ok attempts=1 timing_s=1.250\n"
        "copyright: verbatim notice timing_s=0.100\n"
    )
    assert parse_story_reasons(text) == {
        "license": "mocked sources ok",
        "copyright": "verbatim notice",
    }


def test_main_preflight_fail_skips_workers(monkeypatch):
    """Fail-fast: SystemExit from preflight before any worker starts."""

    def boom(_config):
        raise SystemExit("Preflight failed (claude) after 4 attempts: down")

    monkeypatch.setattr("main.preflight", boom)
    monkeypatch.setattr(
        "main.run_workers",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("workers must not run")),
    )
    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=Path("unused"),
        run_name=None,
        model="claude-haiku-4-5",
        workers=1,
        cache_read=None,
        cache_write=None,
    )
    with pytest.raises(SystemExit, match="Preflight failed"):
        main.run(cfg)


def test_fixture_run_extended_csv_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", _fake_copyright)

    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path / "runs",
        run_name="ops-demo",
        model="claude-opus-4-8",
        workers=2,
        cache_read=None,
        cache_write=None,
    )
    out = main.run(cfg)
    results_path = out / run_dir.results_csv_name(cfg.model, 3)
    ext_path = results_path.with_name(results_path.stem + "_extended.csv")
    assert ext_path.is_file()
    with ext_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert "cache_hit" in rows[0]
    assert rows[0]["cache_hit"] == "false"
    assert "inferencer_cost_usd" in rows[0]
    # Fake infer returns plain dict → empty CallMeta (0 calls) → $0, not unknown.
    assert rows[0]["inferencer_cost_usd"] == "0.000000"
    assert "download_attempts" in rows[0]
    assert rows[0]["download_attempts"]
    assert "inferencer_elapsed_s" in rows[0]
    assert rows[0]["inferencer_elapsed_s"]  # from Story timing_s=
    assert rows[0]["license_reasoning"] == "mocked sources ok"
    assert rows[0]["copyright_reasoning"] == "verbatim notice"

    summary_path = out / "summary.json"
    assert summary_path.is_file()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["run_name"] == "ops-demo"
    assert payload["model"] == "claude-opus-4-8"
    assert payload["workers"] == 2
    assert payload["components"] == 3
    assert "started_at_utc" in payload and "ended_at_utc" in payload
    costs = payload["costs"]
    assert "license_inference" in costs
    assert "copyright_extraction" in costs
    assert set(costs["equality_judges"]) == {"license", "url", "copyright"}
    # Fakes return plain dict → empty CallMeta → known $0, not unknown.
    assert costs["total_usd"] == "0.000000"
    assert costs["license_inference"]["total_usd"] == "0.000000"
    assert costs["license_inference"]["unknown_cost_calls"] == 0
    assert "saved_by_cache_usd" in costs["license_inference"]
    timings = payload["timings"]
    assert timings["wall_seconds"] >= 0
    assert timings["avg_seconds_per_row"] is not None
    assert timings["avg_infer_seconds"] is not None
    assert timings["avg_download_seconds"] is not None
    assert timings["avg_copyright_seconds"] is not None


def test_build_summary_cache_hit_zero_cost(tmp_path):
    from datetime import datetime, timezone

    from input_csv import Component
    from pipeline import ComponentResult

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    hit = ComponentResult(component=comp, from_cache=True)
    miss = ComponentResult(component=comp, from_cache=False)
    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path,
        run_name=None,
        model="claude-haiku-4-5",
        workers=1,
        cache_read=None,
        cache_write=None,
    )
    now = datetime.now(timezone.utc)
    payload = build_summary(
        cfg, tmp_path, [hit, miss], started_at=now, ended_at=now, wall_seconds=1.0
    )
    assert payload["cache_hits"] == 1
    # Empty CallMeta on both → known $0, zero unknown calls.
    assert payload["costs"]["license_inference"]["unknown_cost_calls"] == 0
    assert payload["costs"]["license_inference"]["total_usd"] == "0.000000"
    assert payload["costs"]["total_usd"] == "0.000000"


def test_build_summary_rolls_up_numeric_metas(tmp_path):
    from datetime import datetime, timezone

    from input_csv import Component
    from pipeline import ComponentResult

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    lic = CallMeta()
    lic.add_call(cost_usd=0.01, raw="lic")
    cp = CallMeta()
    cp.add_call(cost_usd=0.02, raw="cp")
    result = ComponentResult(
        component=comp,
        license_meta=lic,
        copyright_meta=cp,
    )
    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path,
        run_name=None,
        model="claude-haiku-4-5",
        workers=1,
        cache_read=None,
        cache_write=None,
    )
    now = datetime.now(timezone.utc)
    payload = build_summary(
        cfg, tmp_path, [result], started_at=now, ended_at=now, wall_seconds=1.0
    )
    costs = payload["costs"]
    assert costs["license_inference"]["total_usd"] == "0.010000"
    assert costs["copyright_extraction"]["total_usd"] == "0.020000"
    assert costs["total_usd"] == "0.030000"
    assert costs["avg_per_row_usd"] == "0.030000"


def test_build_summary_unknown_meta_forces_unknown(tmp_path):
    from datetime import datetime, timezone

    from input_csv import Component
    from pipeline import ComponentResult

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    lic = CallMeta()
    lic.add_call(cost_usd=0.01, raw="ok")
    bad = CallMeta()
    bad.add_call(cost_usd=None, raw="no-price")
    result = ComponentResult(
        component=comp,
        license_meta=lic,
        copyright_meta=bad,
    )
    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path,
        run_name=None,
        model="claude-haiku-4-5",
        workers=1,
        cache_read=None,
        cache_write=None,
    )
    now = datetime.now(timezone.utc)
    payload = build_summary(
        cfg, tmp_path, [result], started_at=now, ended_at=now, wall_seconds=1.0
    )
    costs = payload["costs"]
    assert costs["license_inference"]["total_usd"] == "0.010000"
    assert costs["copyright_extraction"]["total_usd"] == UNKNOWN_COST
    assert costs["copyright_extraction"]["unknown_cost_calls"] == 1
    assert costs["total_usd"] == UNKNOWN_COST
    assert costs["avg_per_row_usd"] == UNKNOWN_COST