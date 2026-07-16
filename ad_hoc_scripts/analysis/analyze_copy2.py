"""Re-run latency + copyright-path analysis on the fresh mid-run copy (Copy (2)),
and identify FROZEN components: per_component dir exists (started) but no
finished CSV row, plus where their story.txt stalled. Read-only.
"""
from __future__ import annotations

import csv
import json
import re
import statistics as st
from pathlib import Path

RUN = Path(__file__).resolve().parents[2] / "runs" / "20260716_102127_ClaudeOpu-4-8_380 - Copy (2)"
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
with CSV.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
    r = csv.DictReader(f)
    hdr = r.fieldnames
    for row in r:
        if len(row) < len(hdr) or any(k is None for k in row) or not row.get("component_name"):
            continue
        rows.append(row)

base_dirs = [d for d in PC.iterdir() if d.is_dir() and "__eq_" not in d.name]
print(f"CSV finished rows: {len(rows)}")
print(f"per_component base dirs (started): {len(base_dirs)}")
print()

infer = [fnum(r.get("inferencer_elapsed_s")) for r in rows]
copyr = [fnum(r.get("copyright_elapsed_s")) for r in rows]
total = [fnum(r.get("total_elapsed_s")) for r in rows]

summarize("inferencer_elapsed_s", infer)
summarize("copyright_elapsed_s", copyr)
summarize("total_elapsed_s", total)

web = sum(1 for r in rows if str(r.get("copyright_reasoning", "")).startswith("web:"))
npm = sum(1 for r in rows if r.get("copyright_reasoning") == "npm_author")
print(f"\ncopyright via web(2nd Claude): {web}  via npm: {npm}  (of {len(rows)})")

resid = []
for r in rows:
    t, i, c = fnum(r["total_elapsed_s"]), fnum(r["inferencer_elapsed_s"]), fnum(r["copyright_elapsed_s"])
    if None not in (t, i, c):
        resid.append(t - i - c)
summarize("residual(total-inf-cp)", resid)

# copyright wall by path (the buried GPT pathology)
print("\n=== copyright_elapsed_s by path ===")
buckets = {"web (2nd Opus)": [], "npm_author": [], "file/other (GPT only)": []}
for r in rows:
    t = fnum(r.get("copyright_elapsed_s"))
    if t is None:
        continue
    reason = (r.get("copyright_reasoning") or "")
    if reason.startswith("web:"):
        buckets["web (2nd Opus)"].append(t)
    elif reason == "npm_author":
        buckets["npm_author"].append(t)
    else:
        buckets["file/other (GPT only)"].append(t)
for name, vals in buckets.items():
    if not vals:
        print(f" {name:24s} n=0"); continue
    print(f" {name:24s} n={len(vals):3d} mean={st.mean(vals):6.1f} "
          f"med={st.median(vals):6.1f} min={min(vals):5.1f} max={max(vals):6.1f}")

# --- FROZEN components: dir started but no finished CSV row ---
finished_names = {r.get("component_name") for r in rows}
print("\n=== FROZEN components (started dir, no finished CSV row) ===")
frozen = []
for d in base_dirs:
    mp = d / "meta.json"
    name = None
    if mp.exists():
        try:
            name = json.loads(mp.read_text(encoding="utf-8", errors="replace")).get("component_name")
        except Exception:
            pass
    if name is None:
        name = d.name
    if name not in finished_names:
        frozen.append((name, d))

print(f"frozen count: {len(frozen)}")


def stall_stage(last_line: str) -> str:
    """Which pipeline stage did this component stall AT (last completed step)?"""
    if not last_line:
        return "0 never-started (only meta.json, no story)"
    ll = last_line
    if ll.startswith("is_eq_copyright="):
        return "6 done-body (finished last equality, not in CSV)"
    if ll.startswith("is_eq_license_code_url="):
        return "5 stuck in copyright equality judge"
    if ll.startswith("is_eq_license_name="):
        return "4 stuck in url-content equality (download+judge)"
    if ll.startswith("copyright:"):
        return "3 stuck entering equality (license_name judge)"
    if ll.startswith("download:"):
        return "2 stuck in resolve_copyright (GPT extract / web) after download"
    if ll.startswith("license:"):
        return "1 stuck in license download"
    return "? other: " + ll[:40]


stage_counts = {}
detail = []
for name, d in frozen:
    sp = d / "story.txt"
    tail = ""
    if sp.exists():
        lines = sp.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        tail = lines[-1] if lines else ""
    stage = stall_stage(tail)
    stage_counts[stage] = stage_counts.get(stage, 0) + 1
    detail.append((stage, name, tail))

print("\n--- frozen by stall stage ---")
for stage in sorted(stage_counts):
    print(f"  {stage_counts[stage]:3d}  {stage}")

print("\n--- frozen detail (stage-sorted, excludes never-started) ---")
for stage, name, tail in sorted(detail):
    if stage.startswith("0 "):
        continue
    print(f"  [{stage[0]}] {name}")
    print(f"        last: {tail[:150]}")
