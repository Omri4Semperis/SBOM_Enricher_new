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
from download import (  # noqa: E402
    is_generic_template,
    looks_like_html,
    nuget_candidates,
    rewrite_viewer_to_raw,
)
from input_csv import parse_component_name  # noqa: E402
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


def gt_is_html_landing(gt_url: str) -> bool:
    """Would production's fetch flag this GT URL `fail_kind='html'` (→ Unscoreable)?
    Mirrors `_try_one`'s order exactly: viewer rewrite, generic-template reject
    (→ 'template', NOT html), then the HTML body/content-type sniff. Skips the
    retry/disk-write machinery a full `fetch_license_file` needs for this read."""
    url = rewrite_viewer_to_raw((gt_url or "").strip())
    if not url or is_generic_template(url):
        return False
    try:
        resp = requests.get(url, timeout=FETCH_TIMEOUT_S)
    except requests.RequestException:
        return False
    if resp.status_code != 200 or not resp.content:
        return False
    return looks_like_html(resp.content, resp.headers.get("Content-Type", ""))


def adjusted_url_grade(row: dict) -> tuple[str, bool]:
    """Real `grade_item`, live-probing the GT URL only for the one reason the
    old code collapses HTML-landing-page and any-other-failure into one
    string ('gt_url_download_failed') — see P4 doc capsule."""
    inferred = row.get("inferred_license_code_url", "")
    is_eq = row.get("is_eq_license_code_url", "") or ""
    probed = False
    if row.get("eq_license_code_url_reason", "") == "gt_url_download_failed":
        probed = True
        if gt_is_html_landing(row.get("license_code_url", "")):
            is_eq = "UNSCOREABLE"
    return grade_item(inferred, is_eq), probed


def copyright_guard_triggered(row: dict) -> bool:
    """Whether the row's inferred copyright trips the association-aware
    stray-holder guard. Reject-only: production continues through the npm +
    web fallback chain after a rejection, so this does not determine the
    row's final grade — count the trigger, don't simulate a grade."""
    inferred = row.get("inferred_copyright", "")
    if not inferred.strip():
        return False
    lib_name, _ = parse_component_name(row.get("component_name", ""))
    return _is_stray_holder(inferred, row.get("purl", ""), lib_name)


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

    # ---- copyright: guard-trigger count only. The guard is reject-only —
    # production continues through the npm + web fallback chain after a
    # rejection — so this offline pass cannot assert a resulting grade for
    # these rows; no movement table. ----
    mismatch_cp = [r for r in rows if grades(r).get("copyright") == "Mismatch"]
    stray_rows = sum(1 for r in mismatch_cp if copyright_guard_triggered(r))
    out("## copyright")
    out(
        f"  {stray_rows} / {len(mismatch_cp)} raw-Mismatch rows carry a holder the "
        "stray-holder guard rejects."
    )
    out(
        "  Production then continues through npm + web fallbacks, so this "
        "offline pass does not determine their final grade "
        "(Hit/Mismatch/Unknown).\n"
    )

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
