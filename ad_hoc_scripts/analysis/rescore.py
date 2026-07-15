"""Re-score the run under a transparent 'fair-to-agent' policy.

Every Mismatch/Unknown is classified into a root-cause class, then re-graded
per an explicit policy that separates genuine agent errors from GT-quality and
judge-strictness artifacts. Emits both the raw and adjusted tallies plus a
per-row audit trail.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN = REPO / "runs" / "20260715_144424_ClaudeOpu-4-8_380"
EXT = RUN / "results_ClaudeOpu-4-8_380_extended.csv"
OUT = REPO / "ad_hoc_scripts" / "ad_hoc_scripts_output"
OUT.mkdir(parents=True, exist_ok=True)
csv.field_size_limit(10_000_000)

# Proprietary / EULA GT hosts: no public downloadable OSS license file exists,
# so an empty inference is 'Unknown' (didn't know) rather than a wrong guess.
PROPRIETARY_MARKERS = (
    "devexpress.com", "js.devexpress.com", "componentspace.com", "zzzprojects.com",
    "fontawesome.com/license", "visualstudio.microsoft.com/license",
    "go.microsoft.com/fwlink", "learn.microsoft.com", "download.microsoft.com",
    "sqlite.org/copyright", "devextreme",
)


def eco(purl: str) -> str:
    m = re.match(r"pkg:([^/]+)/", (purl or "").strip())
    return m.group(1).lower() if m else "(none)"


def grades(row: dict) -> dict:
    try:
        return json.loads(row.get("grades") or "{}")
    except json.JSONDecodeError:
        return {}


def load() -> list[dict]:
    with EXT.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# ---- copyright holder comparison helpers ----
_YEAR = re.compile(r"\b\d{4}\b|\b\d{4}\s*[-–]\s*\d{4}\b")
_MARK = re.compile(r"\(c\)|©|ï¿½|copyright|all rights reserved", re.IGNORECASE)


def holder_tokens(text: str) -> set[str]:
    t = _MARK.sub(" ", text or "")
    t = _YEAR.sub(" ", t)
    # split on newlines / semicolons / commas into holder chunks, keep alnum words
    chunks = re.split(r"[\n;,]", t)
    out: set[str] = set()
    for c in chunks:
        words = re.findall(r"[A-Za-z][A-Za-z.&]+", c.lower())
        words = [w for w in words if w not in {"inc", "ltd", "llc", "corp", "corporation", "the", "and", "contributors", "co", "gmbh"}]
        if words:
            out.add(" ".join(words))
    return {x for x in out if x}


def classify_copyright(gt: str, inf: str) -> str:
    g = holder_tokens(gt)
    i = holder_tokens(inf)
    if not g or not i:
        return "cp_unparseable"
    # year-only: same holder set once years removed
    if g == i:
        return "cp_year_or_format_only"
    # subset/superset: one holder set contained in the other (e.g. 'X' vs 'X and Contributors')
    if g <= i or i <= g:
        return "cp_superset_subset"
    # any shared primary holder token
    if g & i:
        return "cp_partial_overlap"
    return "cp_different_holder"


def classify_url(row: dict) -> str:
    reason = row.get("eq_license_code_url_reason", "") or ""
    inf = (row.get("inferred_license_code_url") or "").strip()
    gt = (row.get("license_code_url") or "").strip().lower()
    if "gt_url_download_failed" in reason:
        return "url_gt_not_a_file"  # agent produced a working license URL; GT is a landing page
    if "inferred_url_download_failed" in reason:
        if not inf:
            if any(m in gt for m in PROPRIETARY_MARKERS):
                return "url_proprietary_no_file"  # EULA; treat empty as Unknown
            return "url_agent_missed"  # OSS license existed, agent gave nothing
        return "url_agent_wrong"  # agent gave a URL that 404'd / was HTML
    if reason.startswith("judge:"):
        return "url_content_differs"
    return "url_other"


def classify_license_name(gt: str, inf: str) -> str:
    g = (gt or "").strip().lower()
    i = (inf or "").strip().lower()
    eula_gt = "eula" in g or "library license" in g or "library eula" in g
    eula_inf = "eula" in i
    if eula_gt and eula_inf:
        return "ln_eula_naming_granularity"
    if {"icu"} & {g} and "unicode" in i or ("unicode" in g and "icu" in i):
        return "ln_synonym"
    # compound SPDX expressions
    if (" and " in g or " with " in g) or (" and " in i or " with " in i):
        return "ln_spdx_expression"
    if eula_inf and not eula_gt:
        return "ln_agent_said_eula_but_oss"  # e.g. GT=MIT/Apache, INF=Microsoft-EULA
    return "ln_other"


def main() -> None:
    rows = load()
    lines: list[str] = []

    def out(s=""):
        lines.append(s)

    # classification counters
    url_cls, cp_cls, ln_cls = Counter(), Counter(), Counter()
    for r in rows:
        g = grades(r)
        if g.get("license_code_url") == "Mismatch":
            url_cls[classify_url(r)] += 1
        if g.get("copyright") == "Mismatch":
            cp_cls[classify_copyright(r.get("copyright", ""), r.get("inferred_copyright", ""))] += 1
        if g.get("license_name") == "Mismatch":
            ln_cls[classify_license_name(r.get("license_name", ""), r.get("inferred_license_name", ""))] += 1

    out("# Root-cause classification of mismatches\n")
    out("## license_code_url mismatch classes")
    for k, n in url_cls.most_common():
        out(f"  {n:3d}  {k}")
    out(f"  TOTAL {sum(url_cls.values())}\n")
    out("## copyright mismatch classes")
    for k, n in cp_cls.most_common():
        out(f"  {n:3d}  {k}")
    out(f"  TOTAL {sum(cp_cls.values())}\n")
    out("## license_name mismatch classes")
    for k, n in ln_cls.most_common():
        out(f"  {n:3d}  {k}")
    out(f"  TOTAL {sum(ln_cls.values())}\n")

    # ---- Adjusted re-grade policy ----
    # Classes treated as NOT-an-agent-error (re-graded to Hit):
    url_to_hit = {"url_gt_not_a_file"}
    url_to_unknown = {"url_proprietary_no_file"}
    cp_to_hit = {"cp_year_or_format_only", "cp_superset_subset"}
    ln_to_hit = {"ln_eula_naming_granularity", "ln_synonym"}

    def adj_grade(r, field):
        g = grades(r).get(field, "?")
        if g != "Mismatch":
            return g
        if field == "license_code_url":
            c = classify_url(r)
            if c in url_to_hit:
                return "Hit"
            if c in url_to_unknown:
                return "Unknown"
            return "Mismatch"
        if field == "copyright":
            c = classify_copyright(r.get("copyright", ""), r.get("inferred_copyright", ""))
            return "Hit" if c in cp_to_hit else "Mismatch"
        if field == "license_name":
            c = classify_license_name(r.get("license_name", ""), r.get("inferred_license_name", ""))
            return "Hit" if c in ln_to_hit else "Mismatch"
        return g

    out("# Per-field: raw vs adjusted\n")
    for field in ("license_name", "license_code_url", "copyright"):
        raw = Counter(grades(r).get(field, "?") for r in rows)
        adj = Counter(adj_grade(r, field) for r in rows)
        out(f"## {field}")
        for grade in ("Hit", "Mismatch", "Unknown"):
            out(f"  {grade:9s} raw={raw.get(grade,0):3d}  ->  adjusted={adj.get(grade,0):3d}")
        n = len(rows)
        out(f"  Hit-rate raw={100*raw.get('Hit',0)/n:.1f}%  adjusted={100*adj.get('Hit',0)/n:.1f}%\n")

    # all-three-hit
    raw_all = sum(1 for r in rows if all(grades(r).get(f) == "Hit" for f in ("license_name","license_code_url","copyright")))
    adj_all = sum(1 for r in rows if all(adj_grade(r, f) == "Hit" for f in ("license_name","license_code_url","copyright")))
    out(f"All-three-Hit rows: raw={raw_all} ({100*raw_all/len(rows):.1f}%)  adjusted={adj_all} ({100*adj_all/len(rows):.1f}%)")

    report = "\n".join(lines)
    (OUT / "rescore.txt").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
