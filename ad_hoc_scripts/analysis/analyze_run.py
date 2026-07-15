"""Ad hoc analysis of a run's extended results CSV.

Buckets Hit/Mismatch/Unknown per field, breaks down the mismatches by
root-cause signal (equality reason prefix, ecosystem, empty-inference,
download failure), and dumps representative examples for manual review.

Usage:
    .venv\\Scripts\\python.exe ad_hoc_scripts/analysis/analyze_run.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN = REPO / "runs" / "20260715_144424_ClaudeOpu-4-8_380"
EXT = RUN / "results_ClaudeOpu-4-8_380_extended.csv"
OUT = REPO / "ad_hoc_scripts" / "ad_hoc_scripts_output"
OUT.mkdir(parents=True, exist_ok=True)

FIELDS = ("license_name", "license_code_url", "copyright")


def ecosystem(purl: str) -> str:
    m = re.match(r"pkg:([^/]+)/", (purl or "").strip())
    return m.group(1).lower() if m else "(none)"


def reason_bucket(reason: str) -> str:
    r = (reason or "").strip()
    if not r:
        return "(empty)"
    if r.startswith("judge:"):
        return "judge:FALSE (content differs)"
    if r.startswith("judge_bad_verdict"):
        return "judge_bad_verdict"
    # non-judge ladder reasons: identical / normalized / no_judge /
    # inferred_url_download_failed / gt_url_download_failed
    return r


def load_rows() -> list[dict]:
    with EXT.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_grades(row: dict) -> dict:
    try:
        return json.loads(row.get("grades") or "{}")
    except json.JSONDecodeError:
        return {}


def main() -> None:
    rows = load_rows()
    lines: list[str] = []

    def out(s: str = "") -> None:
        lines.append(s)

    out(f"# Run analysis: {RUN.name}")
    out(f"Rows: {len(rows)}")
    out()

    # Per-field grade tallies
    for field in FIELDS:
        c = Counter(parse_grades(r).get(field, "?") for r in rows)
        total = sum(c.values())
        out(f"## {field}")
        for grade in ("Hit", "Mismatch", "Unknown", "?"):
            if c.get(grade):
                out(f"  {grade}: {c[grade]} ({100*c[grade]/total:.1f}%)")
        out()

    # ---- license_code_url mismatch breakdown ----
    out("## license_code_url MISMATCH breakdown")
    url_mismatch = [r for r in rows if parse_grades(r).get("license_code_url") == "Mismatch"]
    out(f"Total URL mismatches: {len(url_mismatch)}")
    out()
    by_reason = Counter(reason_bucket(r.get("eq_license_code_url_reason", "")) for r in url_mismatch)
    out("### by equality reason")
    for reason, n in by_reason.most_common():
        out(f"  {n:3d}  {reason}")
    out()
    # empty inferred URL?
    empty_inf = sum(1 for r in url_mismatch if not (r.get("inferred_license_code_url") or "").strip())
    out(f"### inferred_license_code_url EMPTY among URL mismatches: {empty_inf}")
    out()
    by_eco = Counter(ecosystem(r.get("purl", "")) for r in url_mismatch)
    out("### by ecosystem")
    for eco, n in by_eco.most_common():
        out(f"  {n:3d}  {eco}")
    out()

    # cross: reason x ecosystem
    out("### reason x ecosystem")
    cross = defaultdict(Counter)
    for r in url_mismatch:
        cross[reason_bucket(r.get("eq_license_code_url_reason", ""))][ecosystem(r.get("purl", ""))] += 1
    for reason, ecoc in sorted(cross.items(), key=lambda kv: -sum(kv[1].values())):
        parts = ", ".join(f"{e}:{n}" for e, n in ecoc.most_common())
        out(f"  {sum(ecoc.values()):3d}  {reason}  [{parts}]")
    out()

    # ---- copyright mismatch breakdown ----
    out("## copyright MISMATCH breakdown")
    cp_mismatch = [r for r in rows if parse_grades(r).get("copyright") == "Mismatch"]
    out(f"Total copyright mismatches: {len(cp_mismatch)}")
    by_reason = Counter(reason_bucket(r.get("eq_copyright_reason", "")) for r in cp_mismatch)
    out("### by equality reason")
    for reason, n in by_reason.most_common():
        out(f"  {n:3d}  {reason}")
    out()
    by_eco = Counter(ecosystem(r.get("purl", "")) for r in cp_mismatch)
    out("### by ecosystem")
    for eco, n in by_eco.most_common():
        out(f"  {n:3d}  {eco}")
    out()

    # ---- license_name mismatch breakdown ----
    out("## license_name MISMATCH breakdown")
    ln_mismatch = [r for r in rows if parse_grades(r).get("license_name") == "Mismatch"]
    out(f"Total license_name mismatches: {len(ln_mismatch)}")
    by_eco = Counter(ecosystem(r.get("purl", "")) for r in ln_mismatch)
    out("### by ecosystem")
    for eco, n in by_eco.most_common():
        out(f"  {n:3d}  {eco}")
    out()

    report = "\n".join(lines)
    (OUT / "run_analysis_summary.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
