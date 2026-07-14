"""Streaming results.csv writer (audit-aware triplet column order)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import ComponentResult

# Locked order: GT → inferred → is_eq when GT present; else inferred only.
_ITEM_TRIPLETS = (
    ("license_name", "inferred_license_name", "is_eq_license_name"),
    ("license_code_url", "inferred_license_code_url", "is_eq_license_code_url"),
    ("copyright", "inferred_copyright", "is_eq_copyright"),
)

GT_COLUMNS = tuple(t[0] for t in _ITEM_TRIPLETS)


def detect_gt_columns(extra_columns: list[str] | tuple[str, ...]) -> list[str]:
    """Ground-truth columns present in input header, locked item order."""
    extras = set(extra_columns)
    return [c for c in GT_COLUMNS if c in extras]


def build_fieldnames(
    gt_columns: list[str] | tuple[str, ...],
    passthrough: list[str] | tuple[str, ...],
) -> list[str]:
    gt = set(gt_columns)
    names = ["component_name", "purl"]
    for gt_col, inferred, is_eq in _ITEM_TRIPLETS:
        if gt_col in gt:
            names.extend([gt_col, inferred, is_eq])
        else:
            names.append(inferred)
    names.extend(passthrough)
    return names


class ResultsWriter:
    def __init__(self, path: Path, extra_columns: list[str]) -> None:
        self._path = path
        self._gt_columns = detect_gt_columns(extra_columns)
        self._passthrough = [c for c in extra_columns if c not in GT_COLUMNS]
        self._fieldnames = build_fieldnames(self._gt_columns, self._passthrough)
        self._file = path.open("w", newline="", encoding="utf-8-sig")
        self._writer = csv.DictWriter(self._file, fieldnames=self._fieldnames)
        self._writer.writeheader()
        self._file.flush()

    @property
    def gt_columns(self) -> list[str]:
        return list(self._gt_columns)

    def write_row(self, result: ComponentResult) -> None:
        extras = result.component.extras
        row: dict[str, str] = {
            "component_name": result.component.component_name,
            "purl": result.component.purl,
            "inferred_license_name": result.inferred_license_name,
            "inferred_license_code_url": result.inferred_license_code_url,
            "inferred_copyright": result.inferred_copyright,
        }
        if "license_name" in self._gt_columns:
            row["license_name"] = extras.get("license_name", "")
            row["is_eq_license_name"] = result.is_eq_license_name
        if "license_code_url" in self._gt_columns:
            row["license_code_url"] = extras.get("license_code_url", "")
            row["is_eq_license_code_url"] = result.is_eq_license_code_url
        if "copyright" in self._gt_columns:
            row["copyright"] = extras.get("copyright", "")
            row["is_eq_copyright"] = result.is_eq_copyright
        for col in self._passthrough:
            row[col] = extras.get(col, "")
        self._writer.writerow(row)
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> ResultsWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
