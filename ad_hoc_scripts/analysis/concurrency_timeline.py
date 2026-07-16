"""Reconstruct concurrency timeline from story.txt mtimes + total_elapsed_s.

If the copy preserved mtimes, story.txt mtime ~= component finish time.
start = finish - total_elapsed_s. Overlap => effective concurrency.
Read-only.
"""
from __future__ import annotations

import csv
from pathlib import Path

RUN = Path(__file__).resolve().parents[2] / "runs" / "20260716_102127_ClaudeOpu-4-8_380 - Copy"
CSV = RUN / "results_ClaudeOpu-4-8_380_extended.csv"
PC = RUN / "per_component"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


rows = []
with CSV.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
    r = csv.DictReader(f)
    for row in r:
        if any(k is None for k in row):
            continue
        rows.append(row)

# tail-timeout evidence
inf_over = sum(1 for x in (fnum(r.get("inferencer_elapsed_s")) for r in rows) if x and x > 300)
cp_over = sum(1 for x in (fnum(r.get("copyright_elapsed_s")) for r in rows) if x and x > 300)
tot = len(rows)
print(f"rows={tot}")
print(f"inferencer calls >300s: {inf_over} ({100*inf_over/tot:.0f}%)")
print(f"copyright  calls >300s: {cp_over} ({100*cp_over/tot:.0f}%)")

# elapsed by component_name from CSV
import json
te_by_name = {}
for r in rows:
    name = r.get("component_name")
    te = fnum(r.get("total_elapsed_s"))
    if name and te is not None:
        te_by_name[name] = te

# build finish/start intervals: iterate dirs, map via meta.json, mtime=finish
intervals = []
mts = []
matched = 0
for d in PC.iterdir():
    if not d.is_dir() or "__eq_" in d.name:
        continue
    sp = d / "story.txt"
    mp = d / "meta.json"
    if not (sp.exists() and mp.exists()):
        continue
    try:
        name = json.loads(mp.read_text(encoding="utf-8", errors="replace")).get("component_name")
    except Exception:
        continue
    te = te_by_name.get(name)
    if te is None:
        continue
    matched += 1
    finish = sp.stat().st_mtime
    mts.append(finish)
    intervals.append((finish - te, finish))
print(f"matched dirs->CSV: {matched}")

if mts:
    span = max(mts) - min(mts)
    print(f"\nstory.txt mtime span: {span:.0f}s across {len(mts)} comps "
          f"(if ~run length, mtimes preserved)")

# sweep-line max concurrency + avg concurrency over active window
events = []
for s, e in intervals:
    events.append((s, 1))
    events.append((e, -1))
events.sort()
cur = mx = 0
for _, d in events:
    cur += d
    mx = max(mx, cur)
print(f"max overlapping components (effective concurrency ceiling): {mx}")

# avg concurrency = sum(durations)/window
if intervals:
    t0 = min(s for s, _ in intervals)
    t1 = max(e for _, e in intervals)
    window = t1 - t0
    busy = sum(e - s for s, e in intervals)
    print(f"window={window:.0f}s  sum_durations={busy:.0f}s  "
          f"avg_concurrency=busy/window={busy/window:.1f}")
