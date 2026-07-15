"""Audit scoring: grade Hit/Mismatch/Unknown and write score.csv tally."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

# Ground-truth column names in locked enrichment-field order
GT_FIELDS = ("license_name", "license_code_url", "copyright")

_INFERRED = {
    "license_name": "inferred_license_name",
    "license_code_url": "inferred_license_code_url",
    "copyright": "inferred_copyright",
}
_IS_EQ = {
    "license_name": "is_eq_license_name",
    "license_code_url": "is_eq_license_code_url",
    "copyright": "is_eq_copyright",
}


def grade_item(inferred: str, is_eq: str) -> str:
    """Hit / Mismatch / Unknown (didn't know, didn't guess wrong)."""
    if (inferred or "").strip() == "UNKNOWN":
        return "Unknown"
    if is_eq == "TRUE":
        return "Hit"
    return "Mismatch"


def grade_row(
    result,
    gt_columns: list[str] | tuple[str, ...],
) -> dict[str, str]:
    """Return {gt_col: Hit|Mismatch|Unknown} for each graded field on this result."""
    grades: dict[str, str] = {}
    for gt in gt_columns:
        if gt not in _INFERRED:
            continue
        inferred = getattr(result, _INFERRED[gt])
        is_eq = getattr(result, _IS_EQ[gt], "") or ""
        grades[gt] = grade_item(inferred, is_eq)
    return grades


def tally_grades(
    rows: list[dict[str, str]],
    gt_columns: list[str] | tuple[str, ...],
) -> list[dict[str, str]]:
    """Collapse per-row grade dicts into score.csv rows (Count > 0 only)."""
    cols = [c for c in GT_FIELDS if c in gt_columns]
    if not cols:
        return []
    counter: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        key = tuple(row[c] for c in cols)
        counter[key] += 1
    out: list[dict[str, str]] = []
    for key, count in sorted(counter.items()):
        rec = {cols[i]: key[i] for i in range(len(cols))}
        rec["Count"] = str(count)
        out.append(rec)
    return out


def write_score_csv(
    path: Path,
    results: list,
    gt_columns: list[str] | tuple[str, ...],
) -> Path | None:
    """Write score.csv; return path, or None if no GT columns."""
    cols = [c for c in GT_FIELDS if c in gt_columns]
    if not cols:
        return None
    graded = [getattr(r, "grades", None) or grade_row(r, cols) for r in results]
    rows = tally_grades(graded, cols)
    fieldnames = cols + ["Count"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
