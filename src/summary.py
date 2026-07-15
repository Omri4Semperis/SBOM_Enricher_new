"""Run-level summary.json aggregates."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pricing import UNKNOWN_COST, combine, format_cost

if TYPE_CHECKING:
    from config import Config
    from pipeline import ComponentResult

_TIMING_RE = re.compile(
    r"^(license|download|copyright):.*\btiming_s=([0-9.]+)",
    re.MULTILINE,
)
_LICENSE_REASON_RE = re.compile(
    r"^license:\s+(.*?)\s+attempts=", re.MULTILINE
)
_COPYRIGHT_REASON_RE = re.compile(
    r"^copyright:\s+(.*?)\s+timing_s=", re.MULTILINE
)


def parse_story_timings(story_text: str) -> dict[str, float]:
    """Extract per-phase seconds from Story lines (P8-owned; no pipeline edit)."""
    out: dict[str, float] = {}
    for kind, val in _TIMING_RE.findall(story_text):
        out[kind] = float(val)
    return out


def parse_story_reasons(story_text: str) -> dict[str, str]:
    """Extract license/copyright reasoning text from Story (P8-owned)."""
    out: dict[str, str] = {}
    m = _LICENSE_REASON_RE.search(story_text)
    if m:
        out["license"] = m.group(1).strip()
    m = _COPYRIGHT_REASON_RE.search(story_text)
    if m:
        out["copyright"] = m.group(1).strip()
    return out


def _story_for(run_dir: Path, result: ComponentResult) -> str:
    path = run_dir / "per_component" / result.component.slug / "story.txt"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _cost_bucket(
    *,
    total_usd: float | None,
    n: int,
    unknown_calls: int,
) -> dict:
    return {
        "total_usd": format_cost(total_usd),
        "avg_per_row_usd": (
            format_cost(total_usd / n if n and total_usd is not None else None)
            if total_usd is not None
            else UNKNOWN_COST
        ),
        "unknown_cost_calls": unknown_calls,
    }


def build_summary(
    config: Config,
    run_dir: Path,
    results: list[ComponentResult],
    *,
    started_at: datetime,
    ended_at: datetime,
    wall_seconds: float,
) -> dict:
    n = len(results)
    cache_hits = sum(1 for r in results if r.from_cache)

    license_m = combine(r.license_meta for r in results)
    copyright_m = combine(r.copyright_meta for r in results)
    eq_name_m = combine(r.eq_license_name_meta for r in results)
    eq_url_m = combine(r.eq_license_code_url_meta for r in results)
    eq_cp_m = combine(r.eq_copyright_meta for r in results)
    run_m = combine([license_m, copyright_m, eq_name_m, eq_url_m, eq_cp_m])
    run_total = run_m.total_usd()

    infer_times: list[float] = []
    dl_times: list[float] = []
    cr_times: list[float] = []
    for r in results:
        t = parse_story_timings(_story_for(run_dir, r))
        if "license" in t:
            infer_times.append(t["license"])
        if "download" in t:
            dl_times.append(t["download"])
        if "copyright" in t:
            cr_times.append(t["copyright"])

    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 6) if vals else None

    costs = {
        "license_inference": _cost_bucket(
            total_usd=license_m.total_usd(),
            n=n,
            unknown_calls=license_m.unknown_calls,
        ),
        "copyright_extraction": _cost_bucket(
            total_usd=copyright_m.total_usd(),
            n=n,
            unknown_calls=copyright_m.unknown_calls,
        ),
        "equality_judges": {
            "license": _cost_bucket(
                total_usd=eq_name_m.total_usd(),
                n=n,
                unknown_calls=eq_name_m.unknown_calls,
            ),
            "url": _cost_bucket(
                total_usd=eq_url_m.total_usd(),
                n=n,
                unknown_calls=eq_url_m.unknown_calls,
            ),
            "copyright": _cost_bucket(
                total_usd=eq_cp_m.total_usd(),
                n=n,
                unknown_calls=eq_cp_m.unknown_calls,
            ),
        },
        "total_usd": format_cost(run_total),
        "avg_per_row_usd": (
            format_cost(run_total / n if n and run_total is not None else None)
            if run_total is not None
            else UNKNOWN_COST
        ),
    }

    return {
        "run_info": {
            "run_dir": str(run_dir),
            "run_id": run_dir.name,
            "run_name": config.run_name,
            "model": config.model,
            "workers": config.workers,
            "components": n,
            "cache_hits": cache_hits,
            "started_at_utc": started_at.astimezone(timezone.utc).isoformat(),
            "ended_at_utc": ended_at.astimezone(timezone.utc).isoformat(),
        },
        "costs": costs,
        "timings": {
            "wall_seconds": round(wall_seconds, 6),
            "avg_seconds_per_row": round(wall_seconds / n, 6) if n else None,
            "avg_infer_seconds": _avg(infer_times),
            "avg_download_seconds": _avg(dl_times),
            "avg_copyright_seconds": _avg(cr_times),
            "avg_equality_seconds": None,  # not captured on Story yet
        },
    }


def write_summary(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
