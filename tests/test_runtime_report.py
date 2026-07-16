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
    # The extended CSV is written by the app in every run (audit or not). Its
    # inferred/reasoning/cost/file columns feed ADR-0010's expand UI; the GT,
    # is_eq, grades and eq_*_reason columns exist only in audit mode.
    ext = run_dir / "results_ClaudeOpu-4-8_2_extended.csv"
    fieldnames = [
        "component_name",
        "purl",
        "inferred_license_name",
        "inferred_license_code_url",
        "inferred_copyright",
        "license_reasoning",
        "copyright_reasoning",
        "total_cost_usd",
        "license_file_path",
        "license_file_original_url",
    ]
    foo = {
        "component_name": "foo@1.0",
        "purl": "pkg:npm/foo@1.0",
        "inferred_license_name": "MIT",
        "inferred_license_code_url": "https://raw.example.com/foo/LICENSE",
        "inferred_copyright": "Copyright (c) Foo Authors",
        "license_reasoning": "npm registry metadata lists MIT",
        "copyright_reasoning": "extracted from the downloaded LICENSE file",
        "total_cost_usd": "0.100000",
        "license_file_path": "licenses/foo@1.0.txt",
        "license_file_original_url": "https://raw.example.com/foo/LICENSE",
    }
    bar = {
        "component_name": "bar@2.0",
        "purl": "pkg:nuget/bar@2.0",
        "inferred_license_name": "Apache-2.0",
        "inferred_license_code_url": "",
        "inferred_copyright": "Copyright Bar Inc.",
        "license_reasoning": "nuspec license expression",
        "copyright_reasoning": "nuget author fallback",
        "total_cost_usd": "unknown",
        "license_file_path": "",
        "license_file_original_url": "",
    }
    if with_grades:
        fieldnames = fieldnames + [
            "license_name",
            "license_code_url",
            "copyright",
            "grades",
            "eq_license_name_reason",
            "eq_license_code_url_reason",
            "eq_copyright_reason",
        ]
        foo.update(
            {
                "license_name": "MIT",
                "license_code_url": "https://example.com/LICENSE",
                "copyright": "Copyright Foo Inc.",
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
        bar.update(
            {
                "license_name": "Apache-2.0",
                "license_code_url": "https://example.com/bar/LICENSE",
                "copyright": "Copyright Bar Incorporated",
                "grades": json.dumps(
                    {
                        "license_name": "Hit",
                        "license_code_url": "Mismatch",
                        "copyright": "Unknown",
                    }
                ),
                "eq_license_name_reason": "identical",
                "eq_license_code_url_reason": "inferred_url_download_failed",
                "eq_copyright_reason": (
                    "judge:Both names refer to the commercial license with "
                    "immaterial wording differences but the same terms."
                ),
            }
        )
    with ext.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerow(foo)
        w.writerow(bar)
    return run_dir


def test_fmt_dur_mm_ss():
    from runtime_report import fmt_dur

    assert fmt_dur(None) == "—"
    assert fmt_dur(15) == "00:15"
    assert fmt_dur(10 * 60 + 15) == "10:15"
    assert fmt_dur(59 * 60 + 3) == "59:03"
    assert fmt_dur(60 * 60 + 9) == "60:09"
    assert fmt_dur(2 * 3600 + 3 * 60 + 30) == "123:30"
    assert fmt_dur(0.4) == "00:00"
    assert fmt_dur(0.6) == "00:01"


def test_mmss_hint_on_formatted_times_not_raw_story(tmp_path):
    """Formatted surfaces cue mm:ss (minutes); expand keeps raw timing_s= secs."""
    from runtime_report import _MMSS_HINT

    run_dir = _tiny_run(tmp_path, with_grades=True)
    html = write_runtime_report(run_dir).read_text(encoding="utf-8")
    assert _MMSS_HINT in html
    assert "mm:ss (minutes)" in html
    # Raw story download line (seconds) is passed through unchanged.
    assert "timing_s=" in html or "failed" in html or "chose" in html


def test_write_runtime_report_time_only(tmp_path):
    run_dir = _tiny_run(tmp_path, with_grades=False)
    path = write_runtime_report(run_dir)
    assert path == run_dir / "runtime_report.html"
    html = path.read_text(encoding="utf-8")
    assert "Where did the time go" in html
    assert "foo@1.0" in html
    assert "bar@2.0" in html
    assert ">Accuracy<" not in html


def test_write_runtime_report_no_overwrite(tmp_path):
    run_dir = _tiny_run(tmp_path, with_grades=False)
    first = write_runtime_report(run_dir)
    second = write_runtime_report(run_dir)
    third = write_runtime_report(run_dir)
    assert first == run_dir / "runtime_report.html"
    assert second == run_dir / "runtime_report (1).html"
    assert third == run_dir / "runtime_report (2).html"
    assert first.is_file() and second.is_file() and third.is_file()


def test_sticky_titles_css():
    """Main header + section heads use stacked position:sticky (CSS only)."""
    from runtime_report import CSS

    assert "position:sticky" in CSS
    assert "--sticky-main" in CSS
    assert "header.top{position:sticky" in CSS.replace(" ", "")
    assert ".panel>h2,.panel>.sec-head{position:sticky" in CSS.replace(" ", "")


def test_name_cell_stacks_lib_version_chips(tmp_path):
    """Component column: lib name, version, then grade chips as separate rows."""
    run_dir = _tiny_run(tmp_path, with_grades=True)
    html = write_runtime_report(run_dir).read_text(encoding="utf-8")
    assert "class='cname'" in html
    assert "class='cver'" in html
    assert "class='cmeta'" in html
    assert ">foo</div>" in html
    assert ">1.0</div>" in html
    assert 'class="chips"' in html


def test_equality_judge_badge_and_clip(tmp_path):
    from runtime_report import CSS, _fmt_equality

    plain, html = _fmt_equality("judge:Same license terms overall.")
    assert plain == "Same license terms overall."
    assert "eq-badge" in html and "judge:" not in html
    code_plain, code_html = _fmt_equality("identical")
    assert code_plain == "identical" and "<code>" in code_html

    run_dir = _tiny_run(tmp_path, with_grades=True)
    page = write_runtime_report(run_dir).read_text(encoding="utf-8")
    assert "eq-badge" in page
    assert "LLM judge" in page
    assert "class='clip'" in page
    assert "table-layout:fixed" in CSS
    assert "scrollbar-gutter:stable" in CSS


def test_expand_ui_non_audit_shows_inferred_no_gt(tmp_path):
    """No ground truth: strip still shows inferred values; tabs say 'no GT'
    and no grade tag is rendered (ADR 0010)."""
    run_dir = _tiny_run(tmp_path, with_grades=False)
    html = write_runtime_report(run_dir).read_text(encoding="utf-8")
    # Inferred values reach the expand UI even without an audit.
    assert "MIT" in html
    assert "Copyright (c) Foo Authors" in html
    # Pipeline reasoning surfaces; GT is absent.
    assert "npm registry metadata lists MIT" in html
    assert "no GT" in html
    # No grades -> no grade tag is rendered (the .gtag CSS rule still exists).
    assert "class='gtag'" not in html


def test_load_run_accuracy_section(tmp_path):
    run_dir = _tiny_run(tmp_path, with_grades=True)
    run = load_run(run_dir)
    assert run.audit is not None
    assert set(run.audit.fields) == {
        "license_name",
        "license_code_url",
        "copyright",
    }
    # Extended-CSV display facts are attached to components (ADR 0010).
    foo = next(c for c in run.components if c.name == "foo@1.0")
    assert foo.inferred["license_name"] == "MIT"
    assert foo.gt["copyright"] == "Copyright Foo Inc."
    html = build_html(run)
    assert ">Accuracy<" in html
    assert "Why did mismatches happen" in html
    assert "inferred_url_download_failed" in html


def test_expand_ui_audit_strip_and_tabs(tmp_path):
    """Audit run: strip shows inferred values, tabs render for all three
    fields with GT vs inferred, equality + pipeline reasoning (ADR 0010)."""
    run_dir = _tiny_run(tmp_path, with_grades=True)
    html = write_runtime_report(run_dir).read_text(encoding="utf-8")
    # All three tabs present.
    assert "data-tab='license_name'" in html
    assert "data-tab='license_code_url'" in html
    assert "data-tab='copyright'" in html
    # Strip + tab structure and section controls.
    assert "class='strip'" in html
    assert ">Open all<" in html and ">Close all<" in html
    # GT-vs-inferred rows and reasoning surface.
    assert "Ground truth" in html
    assert "extracted from the downloaded LICENSE file" in html
    # A grade tag is rendered for graded fields.
    assert "class='gtag'" in html
    # URL tab exposes the downloaded-file provenance.
    assert "licenses/foo@1.0.txt" in html


def test_cli_main_writes_custom_out(tmp_path):
    from runtime_report import main

    run_dir = _tiny_run(tmp_path, with_grades=False)
    out = tmp_path / "custom.html"
    assert main([str(run_dir), "--out", str(out)]) == 0
    assert out.is_file()
    assert "Where did the time go" in out.read_text(encoding="utf-8")
