"""Two questions:
1. If we cap Claude calls at T seconds, how many CORRECT results do we lose?
2. Is per-call GPT client construction a real latency cost? Isolate copyright
   time on the non-web path (GPT extract + AAD credential + npm http only).
Read-only.
"""
from __future__ import annotations

import csv
import statistics as st
from pathlib import Path

RUN = Path(__file__).resolve().parents[2] / "runs" / "20260716_102127_ClaudeOpu-4-8_380 - Copy"
CSV = RUN / "results_ClaudeOpu-4-8_380_extended.csv"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


rows = []
with CSV.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
    for row in csv.DictReader(f):
        if any(k is None for k in row) or not row.get("component_name"):
            continue
        rows.append(row)
print(f"rows={len(rows)}\n")

# ---------- Q1: timeout accuracy risk ----------
def outcome_license(r):
    v = (r.get("inferred_license_name") or "").strip().upper()
    if v == "UNKNOWN" or v == "":
        return "UNKNOWN"
    return r.get("is_eq_license_name") or "?"

def outcome_cp(r):
    v = (r.get("inferred_copyright") or "").strip().upper()
    if v == "UNKNOWN" or v == "":
        return "UNKNOWN"
    return r.get("is_eq_copyright") or "?"

print("=== Q1: results on SLOW calls (would be killed by a cap) ===")
for label, elapsed_col, outcome_fn in [
    ("license", "inferencer_elapsed_s", outcome_license),
    ("copyright", "copyright_elapsed_s", outcome_cp),
]:
    print(f"\n-- {label} --")
    for T in (180, 240, 300, 360):
        slow = [r for r in rows if (fnum(r.get(elapsed_col)) or 0) > T]
        if not slow:
            print(f" >{T}s: none")
            continue
        oc = {}
        for r in slow:
            k = outcome_fn(r)
            oc[k] = oc.get(k, 0) + 1
        # "correct" = TRUE verdict; "productive" = non-UNKNOWN (has a value)
        correct = oc.get("TRUE", 0)
        productive = sum(v for k, v in oc.items() if k != "UNKNOWN")
        print(f" >{T}s: n={len(slow):3d}  TRUE(correct)={correct:3d}  "
              f"produced-a-value={productive:3d}  breakdown={oc}")

# baseline accuracy for reference
def acc(rows, fn):
    oc = {}
    for r in rows:
        k = fn(r)
        oc[k] = oc.get(k, 0) + 1
    return oc
print("\nbaseline license outcomes:", acc(rows, outcome_license))
print("baseline copyright outcomes:", acc(rows, outcome_cp))

# ---------- Q2: GPT client / copyright non-web time ----------
print("\n=== Q2: copyright_elapsed_s by path (isolate GPT extract + AAD + npm) ===")
buckets = {"web (2nd Opus call)": [], "npm_author": [], "file/other (GPT only)": []}
for r in rows:
    t = fnum(r.get("copyright_elapsed_s"))
    if t is None:
        continue
    reason = (r.get("copyright_reasoning") or "")
    if reason.startswith("web:"):
        buckets["web (2nd Opus call)"].append(t)
    elif reason == "npm_author":
        buckets["npm_author"].append(t)
    else:
        buckets["file/other (GPT only)"].append(t)
for name, vals in buckets.items():
    if not vals:
        print(f" {name:26s} n=0")
        continue
    print(f" {name:26s} n={len(vals):3d} mean={st.mean(vals):6.1f} "
          f"med={st.median(vals):6.1f} min={min(vals):5.1f} max={max(vals):6.1f}")
print("\nNote: 'file/other' path copyright time == GPT-4.1 extract call + fresh")
print("Gpt41Client() construction (DefaultAzureCredential/AAD token) + npm http.")
