"""Dump detailed per-category examples for manual root-cause review."""

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


def ecosystem(purl: str) -> str:
    m = re.match(r"pkg:([^/]+)/", (purl or "").strip())
    return m.group(1).lower() if m else "(none)"


def grades(row: dict) -> dict:
    try:
        return json.loads(row.get("grades") or "{}")
    except json.JSONDecodeError:
        return {}


def load_rows() -> list[dict]:
    with EXT.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def w(f, s=""):
    f.write(s + "\n")


def main() -> None:
    rows = load_rows()

    # 1) gt_url_download_failed — is the GT url truly dead?
    with (OUT / "url_gt_download_failed.txt").open("w", encoding="utf-8") as f:
        subset = [
            r for r in rows
            if grades(r).get("license_code_url") == "Mismatch"
            and "gt_url_download_failed" in (r.get("eq_license_code_url_reason") or "")
        ]
        w(f, f"gt_url_download_failed: {len(subset)}\n")
        for r in subset:
            w(f, f"- {r['component_name']}  [{ecosystem(r['purl'])}]")
            w(f, f"    purl: {r['purl']}")
            w(f, f"    GT  url: {r.get('license_code_url','')}")
            w(f, f"    INF url: {r.get('inferred_license_code_url','')}")
            w(f, "")

    # 2) inferred_url_download_failed
    with (OUT / "url_inferred_download_failed.txt").open("w", encoding="utf-8") as f:
        subset = [
            r for r in rows
            if grades(r).get("license_code_url") == "Mismatch"
            and "inferred_url_download_failed" in (r.get("eq_license_code_url_reason") or "")
        ]
        w(f, f"inferred_url_download_failed: {len(subset)}\n")
        for r in subset:
            inf = (r.get("inferred_license_code_url") or "").strip()
            w(f, f"- {r['component_name']}  [{ecosystem(r['purl'])}]  {'EMPTY-INF' if not inf else ''}")
            w(f, f"    purl: {r['purl']}")
            w(f, f"    GT  url: {r.get('license_code_url','')}")
            w(f, f"    INF url: {inf}")
            w(f, f"    attempts: {r.get('download_attempts','')}")
            w(f, "")

    # 3) URL judge:FALSE content differs
    with (OUT / "url_judge_false.txt").open("w", encoding="utf-8") as f:
        subset = [
            r for r in rows
            if grades(r).get("license_code_url") == "Mismatch"
            and (r.get("eq_license_code_url_reason") or "").startswith("judge:")
        ]
        w(f, f"url judge:FALSE: {len(subset)}\n")
        for r in subset:
            w(f, f"- {r['component_name']}  [{ecosystem(r['purl'])}]")
            w(f, f"    GT  url: {r.get('license_code_url','')}")
            w(f, f"    INF url: {r.get('inferred_license_code_url','')}")
            w(f, f"    reason: {r.get('eq_license_code_url_reason','')}")
            w(f, "")

    # 4) copyright judge:FALSE
    with (OUT / "copyright_judge_false.txt").open("w", encoding="utf-8") as f:
        subset = [r for r in rows if grades(r).get("copyright") == "Mismatch"]
        w(f, f"copyright mismatches: {len(subset)}\n")
        for r in subset:
            w(f, f"- {r['component_name']}  [{ecosystem(r['purl'])}]")
            w(f, f"    GT : {r.get('copyright','')}")
            w(f, f"    INF: {r.get('inferred_copyright','')}")
            w(f, f"    reason: {r.get('eq_copyright_reason','')}")
            w(f, "")

    # 5) license_name mismatch
    with (OUT / "license_name_mismatch.txt").open("w", encoding="utf-8") as f:
        subset = [r for r in rows if grades(r).get("license_name") == "Mismatch"]
        w(f, f"license_name mismatches: {len(subset)}\n")
        for r in subset:
            w(f, f"- {r['component_name']}  [{ecosystem(r['purl'])}]")
            w(f, f"    GT : {r.get('license_name','')}")
            w(f, f"    INF: {r.get('inferred_license_name','')}")
            w(f, f"    reason: {r.get('eq_license_name_reason','')}")
            w(f, "")

    print("dumped 5 files to", OUT)


if __name__ == "__main__":
    main()
