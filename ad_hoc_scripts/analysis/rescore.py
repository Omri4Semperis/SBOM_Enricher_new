"""Re-score the frozen run using the REAL P1-P3 production functions.

Grading logic is never reimplemented here (DECISIONS H.1a) — this script only
imports `grade_item`, `looks_like_html`, `nuget_candidates`, `_is_stray_holder`
from `src/` and adds bounded live HTTP probes for the two facts that need the
network and cannot be reconstructed from the frozen CSV: whether a GT URL is an
HTML landing page (P1's `Unscoreable`), and whether the P2 NuGet fallback would
now resolve a downloadable LICENSE file.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from copyright import _is_stray_holder  # noqa: E402
from download import looks_like_html, nuget_candidates, rewrite_viewer_to_raw  # noqa: E402
from scoring import grade_item  # noqa: E402

RUN = REPO / "runs" / "20260715_144424_ClaudeOpu-4-8_380"
EXT = RUN / "results_ClaudeOpu-4-8_380_extended.csv"
OUT = REPO / "ad_hoc_scripts" / "ad_hoc_scripts_output"
OUT.mkdir(parents=True, exist_ok=True)
csv.field_size_limit(10_000_000)

FETCH_TIMEOUT_S = 20.0
GRADE_ORDER = ("Hit", "Mismatch", "Unknown", "Unscoreable")


def grades(row: dict) -> dict:
    try:
        return json.loads(row.get("grades") or "{}")
    except json.JSONDecodeError:
        return {}


def load() -> list[dict]:
    with EXT.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def probe_gt_content_type(gt_url: str) -> str:
    """Live probe: 'html' | 'ok' | 'error'. Mirrors the fetch signal `_try_one`
    uses (viewer rewrite + `looks_like_html`), without the retry/disk-write
    machinery a full `fetch_license_file` call would need for a read-only check."""
    url = rewrite_viewer_to_raw((gt_url or "").strip())
    if not url:
        return "error"
    try:
        resp = requests.get(url, timeout=FETCH_TIMEOUT_S)
    except requests.RequestException:
        return "error"
    if resp.status_code != 200 or not resp.content:
        return "error"
    return "html" if looks_like_html(resp.content, resp.headers.get("Content-Type", "")) else "ok"


def adjusted_url_grade(row: dict) -> tuple[str, bool]:
    """Real `grade_item`, live-probing the GT URL only for the one reason the
    old code collapses HTML-landing-page and any-other-failure into one
    string ('gt_url_download_failed') — see P4 doc capsule."""
    inferred = row.get("inferred_license_code_url", "")
    is_eq = row.get("is_eq_license_code_url", "") or ""
    probed = False
    if row.get("eq_license_code_url_reason", "") == "gt_url_download_failed":
        probed = True
        if probe_gt_content_type(row.get("license_code_url", "")) == "html":
            is_eq = "UNSCOREABLE"
    return grade_item(inferred, is_eq), probed


def adjusted_copyright_grade(row: dict) -> tuple[str, bool]:
    """Real `grade_item`; a P3 stray-holder is rejected before `resolve_copyright`
    ever emits it, so simulate that rejection by blanking it before grading."""
    inferred = row.get("inferred_copyright", "")
    is_eq = row.get("is_eq_copyright", "") or ""
    stray = bool(inferred.strip()) and _is_stray_holder(inferred)
    return grade_item("" if stray else inferred, is_eq), stray


def nuget_resolves_now(purl: str) -> bool:
    """True if the P2 fallback would now find a downloadable (non-HTML) file."""
    for url in nuget_candidates(purl):
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT_S)
        except requests.RequestException:
            continue
        if resp.status_code == 200 and resp.content and not looks_like_html(
            resp.content, resp.headers.get("Content-Type", "")
        ):
            return True
    return False


def movement_table(out, field: str, raw: Counter, adj: Counter, n: int) -> None:
    """Hit-rate excludes Unscoreable from the denominator (DECISIONS G2)."""
    out(f"## {field}")
    for grade in GRADE_ORDER:
        r, a = raw.get(grade, 0), adj.get(grade, 0)
        if r or a:
            out(f"  {grade:11s} raw={r:3d}  ->  adjusted={a:3d}")
    n_raw = n - raw.get("Unscoreable", 0)
    n_adj = n - adj.get("Unscoreable", 0)
    out(
        f"  Hit-rate raw={100*raw.get('Hit',0)/n_raw:.1f}%  "
        f"adjusted={100*adj.get('Hit',0)/n_adj:.1f}%\n"
    )


def main() -> None:
    rows = load()
    lines: list[str] = []

    def out(s=""):
        lines.append(s)
        print(s)

    out("# Fact-grade re-score (real grade_item + live probes)\n")

    # ---- license_code_url: raw vs adjusted ----
    raw_url = Counter(grades(r).get("license_code_url", "?") for r in rows)
    adj_url = Counter()
    url_probes = 0
    for r in rows:
        if grades(r).get("license_code_url") != "Mismatch":
            adj_url[grades(r).get("license_code_url", "?")] += 1
            continue
        grade, probed = adjusted_url_grade(r)
        url_probes += probed
        adj_url[grade] += 1
    movement_table(out, "license_code_url", raw_url, adj_url, len(rows))
    out(f"  ({url_probes} GT URLs live content-type-probed)\n")

    # ---- copyright: raw vs adjusted ----
    raw_cp = Counter(grades(r).get("copyright", "?") for r in rows)
    adj_cp = Counter()
    stray_rows = 0
    for r in rows:
        if grades(r).get("copyright") != "Mismatch":
            adj_cp[grades(r).get("copyright", "?")] += 1
            continue
        grade, stray = adjusted_copyright_grade(r)
        stray_rows += stray
        adj_cp[grade] += 1
    movement_table(out, "copyright", raw_cp, adj_cp, len(rows))
    out(f"  ({stray_rows} rows rejected by the stray-holder guard)\n")

    # ---- NuGet fallback recall: empty-URL NuGet rows only (informational —
    # frozen run's inferred URL stays empty; this measures fallback reach, not
    # a grade movement on this run) ----
    nuget_empty = [
        r for r in rows
        if r.get("purl", "").lower().startswith("pkg:nuget/")
        and not (r.get("inferred_license_code_url") or "").strip()
    ]
    nuget_recovered = sum(1 for r in nuget_empty if nuget_resolves_now(r.get("purl", "")))
    out("## NuGet fallback recall (empty-inferred-URL NuGet rows, live probe)")
    out(f"  {nuget_recovered} / {len(nuget_empty)} now resolve to a downloadable LICENSE file\n")

    report = "\n".join(lines)
    (OUT / "rescore.txt").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
