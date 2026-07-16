"""Unit tests for the post-run HTML report (time + optional accuracy)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from runtime_report import build_html, load_run, write_runtime_report


def _write_component(
    run_dir: Path,
    slug: str,
    *,
    name: str,
    purl: str,
    story: str,
) -> None:
    d = run_dir / "per_component" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(
        json.dumps({"component_name": name, "purl": purl}, indent=2) + "\n",
        encoding="utf-8",
    )
    (d / "story.txt").write_text(story, encoding="utf-8")


def _tiny_run(tmp_path: Path, *, with_grades: bool) -> Path:
    run_dir = tmp_path / "20260716_000000_ClaudeOpu-4-8_2"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_info": {
                    "run_dir": str(run_dir),
                    "run_id": run_dir.name,
                    "run_name": None,
                    "model": "claude-opus-4-8",
                    "workers": 2,
                    "components": 2,
                    "cache_hits": 0,
                    "started_at_utc": "2026-07-16T00:00:00+00:00",
                    "ended_at_utc": "2026-07-16T00:01:00+00:00",
                },
                "costs": {"total_usd": "0.100000"},
                "timings": {
                    "wall_seconds": 60.0,
                    "avg_seconds_per_row": 30.0,
                    "avg_infer_seconds": 10.0,
                    "avg_download_seconds": 1.0,
                    "avg_copyright_seconds": 5.0,
                    "avg_equality_seconds": None,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_component(
        run_dir,
        "foo@1.0",
        name="foo@1.0",
        purl="pkg:npm/foo@1.0",
        story=(
            "license: ok attempts=1 timing_s=12.000\n"
            "download: chose https://example.com/LICENSE timing_s=0.500\n"
            "copyright: notice timing_s=3.000\n"
        ),
    )
    _write_component(
        run_dir,
        "bar@2.0",
        name="bar@2.0",
        purl="pkg:nuget/bar@2.0",
        story=(
            "license: ok attempts=1 timing_s=8.000\n"
            "download: failed (download_failed) timing_s=0.100\n"
            "copyright: web timing_s=4.000\n"
        ),
    )
    if with_grades:
        ext = run_dir / "results_ClaudeOpu-4-8_2_extended.csv"
        fieldnames = [
            "component_name",
            "purl",
            "grades",
            "eq_license_name_reason",
            "eq_license_code_url_reason",
            "eq_copyright_reason",
        ]
        with ext.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerow(
                {
                    "component_name": "foo@1.0",
                    "purl": "pkg:npm/foo@1.0",
                    "grades": json.dumps(
                        {
                            "license_name": "Hit",
                            "license_code_url": "Hit",
                            "copyright": "Hit",
                        }
                    ),
                    "eq_license_name_reason": "identical",
                    "eq_license_code_url_reason": "identical",
                    "eq_copyright_reason": "identical",
                }
            )
            w.writerow(
                {
                    "component_name": "bar@2.0",
                    "purl": "pkg:nuget/bar@2.0",
                    "grades": json.dumps(
                        {
                            "license_name": "Hit",
                            "license_code_url": "Mismatch",
                            "copyright": "Unknown",
                        }
                    ),
                    "eq_license_name_reason": "identical",
                    "eq_license_code_url_reason": "inferred_url_download_failed",
                    "eq_copyright_reason": "",
                }
            )
    return run_dir


def test_write_runtime_report_time_only(tmp_path):
    run_dir = _tiny_run(tmp_path, with_grades=False)
    path = write_runtime_report(run_dir)
    assert path == run_dir / "runtime_report.html"
    html = path.read_text(encoding="utf-8")
    assert "Where did the time go" in html
    assert "foo@1.0" in html
    assert "bar@2.0" in html
    assert ">Accuracy<" not in html


def test_load_run_accuracy_section(tmp_path):
    run_dir = _tiny_run(tmp_path, with_grades=True)
    run = load_run(run_dir)
    assert run.audit is not None
    assert set(run.audit.fields) == {
        "license_name",
        "license_code_url",
        "copyright",
    }
    html = build_html(run)
    assert ">Accuracy<" in html
    assert "Why did mismatches happen" in html
    assert "inferred_url_download_failed" in html


def test_cli_main_writes_custom_out(tmp_path):
    from runtime_report import main

    run_dir = _tiny_run(tmp_path, with_grades=False)
    out = tmp_path / "custom.html"
    assert main([str(run_dir), "--out", str(out)]) == 0
    assert out.is_file()
    assert "Where did the time go" in out.read_text(encoding="utf-8")
