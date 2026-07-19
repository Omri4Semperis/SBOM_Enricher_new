"""Write library_approvals_enriched.csv — input rows joined to enrichment results."""

from __future__ import annotations

import csv
from pathlib import Path

ENRICHED = ("license_name", "license_code_url", "copyright")
_FIELD = {
    "license_name": "inferred_license_name",
    "license_code_url": "inferred_license_code_url",
    "copyright": "inferred_copyright",
}


def _bad(ours: str, error: str) -> bool:
    return not ours.strip() or ours.strip() == "UNKNOWN" or bool(error)


def write_enriched_csv(
    path: Path | str,
    fieldnames: list[str],
    rows: list[dict[str, str]],
    results: list,
) -> None:
    path = Path(path)
    by_name = {r.component.component_name: r for r in results}
    present = set(fieldnames)
    out_fields = list(fieldnames) + [c for c in ENRICHED if c not in present]

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            name = (row.get("component_name") or "").strip()
            result = by_name[name]  # KeyError on miss — real bug
            out = dict(row)
            for col in ENRICHED:
                ours = getattr(result, _FIELD[col]) or ""
                if col in present:
                    if not _bad(ours, result.error or ""):
                        out[col] = ours
                else:
                    out[col] = ours
            writer.writerow(out)
