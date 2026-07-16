"""Parse the mid-run copy for per-stage latency. Read-only, discards torn rows."""
from __future__ import annotations

import csv
import re
import statistics as st
from pathlib import Path

RUN = Path(__file__).resolve().parents[2] / "runs" / "20260716_102127_ClaudeOpu-4-8_380 - Copy"
CSV = RUN / "results_ClaudeOpu-4-8_380_extended.csv"
PC = RUN / "per_component"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def pct(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, int(round((p / 100) * (len(vals) - 1)))))
    return vals[k]


def summarize(name, vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        print(f"{name:28s} n=0")
        return
    print(f"{name:28s} n={len(vals):3d} sum={sum(vals):9.1f} mean={st.mean(vals):7.1f} "
          f"med={st.median(vals):7.1f} p90={pct(vals,90):7.1f} max={max(vals):7.1f}")


# --- CSV rows (skip torn last line) ---
rows = []
with CSV.open("r", encoding="utf-8", errors="replace", newline="") as f:
    r = csv.DictReader(f)
    hdr = r.fieldnames
    for row in r:
        # torn row guard: must have all expected fields non-None
        if len(row) < len(hdr) or any(k is None for k in row):
            continue
        rows.append(row)

print(f"CSV complete rows: {len(rows)}")
print(f"per_component base dirs: {len([d for d in PC.iterdir() if d.is_dir() and '__eq_' not in d.name])}")
print()

infer = [fnum(r.get("inferencer_elapsed_s")) for r in rows]
copyr = [fnum(r.get("copyright_elapsed_s")) for r in rows]
total = [fnum(r.get("total_elapsed_s")) for r in rows]
cache = [r.get("cache_hit") for r in rows]

summarize("inferencer_elapsed_s", infer)
summarize("copyright_elapsed_s", copyr)
summarize("total_elapsed_s", total)
print()
print("cache_hit values:", {v: cache.count(v) for v in set(cache)})

# copyright path: did it use web (2nd Claude call)?
web = sum(1 for r in rows if str(r.get("copyright_reasoning", "")).startswith("web:"))
npm = sum(1 for r in rows if r.get("copyright_reasoning") == "npm_author")
unknown_cp = sum(1 for r in rows if str(r.get("inferred_copyright","")).upper() == "UNKNOWN")
print(f"\ncopyright via web(2nd Claude): {web}  via npm: {npm}  UNKNOWN: {unknown_cp}  (of {len(rows)})")

# total vs infer+copyright residual (download+equality+overhead)
resid = []
for r in rows:
    t, i, c = fnum(r["total_elapsed_s"]), fnum(r["inferencer_elapsed_s"]), fnum(r["copyright_elapsed_s"])
    if None not in (t, i, c):
        resid.append(t - i - c)
summarize("residual(total-inf-cp)", resid)

# --- story attempts / retries scan ---
att_re = re.compile(r"attempts=(\d+)")
attempts_gt1 = 0
attempts_total = 0
judged_names = judged_cp = judged_url = 0
for d in PC.iterdir():
    if not d.is_dir() or "__eq_" in d.name:
        continue
    sp = d / "story.txt"
    if not sp.exists():
        continue
    txt = sp.read_text(encoding="utf-8", errors="replace")
    m = att_re.search(txt)
    if m:
        attempts_total += 1
        if int(m.group(1)) > 1:
            attempts_gt1 += 1
    if "judge:" in txt:
        judged_names += txt.count("(judge:")
print(f"\nstory license attempts>1: {attempts_gt1} / {attempts_total} (rest attempts=1)")
print(f"story judge: invocations (any field): {judged_names}")
