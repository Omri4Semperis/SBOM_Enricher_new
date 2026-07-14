"""Streaming results.csv writer (audit-aware triplet column order)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING

from pricing import UNKNOWN_COST
from summary import parse_story_timings

if TYPE_CHECKING:
    from pipeline import ComponentResult

# Locked order: GT → inferred → is_eq when GT present; else inferred only.
_ITEM_TRIPLETS = (
    ("license_name", "inferred_license_name", "is_eq_license_name"),
    ("license_code_url", "inferred_license_code_url", "is_eq_license_code_url"),
    ("copyright", "inferred_copyright", "is_eq_copyright"),
)

GT_COLUMNS = tuple(t[0] for t in _ITEM_TRIPLETS)

# Extended CSV append columns (raw/cost empty until earlier phases capture them).
EXTENDED_EXTRA_COLUMNS = (
    "cache_hit",
    "inferencer_raw_response",
    "license_reasoning",
    "inferencer_elapsed_s",
    "inferencer_cost_usd",
    "download_attempts",
    "license_file_path",
    "license_file_original_url",
    "copyright_raw_response",
    "copyright_reasoning",
    "copyright_elapsed_s",
    "copyright_cost_usd",
    "eq_license_name_reason",
    "eq_license_code_url_reason",
    "eq_copyright_reason",
    "eq_license_name_cost_usd",
    "eq_license_code_url_cost_usd",
    "eq_copyright_cost_usd",
    "grades",
    "total_elapsed_s",
    "total_cost_usd",
)


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


def extended_csv_path(results_csv: Path) -> Path:
    return results_csv.with_name(results_csv.stem + "_extended.csv")


class ExtendedWriter:
    """results_*_extended.csv — main columns plus raw/cost/cache/phase detail."""

    def __init__(self, path: Path, extra_columns: list[str], run_dir: Path) -> None:
        self._run_dir = run_dir
        self._gt_columns = detect_gt_columns(extra_columns)
        self._passthrough = [c for c in extra_columns if c not in GT_COLUMNS]
        self._fieldnames = (
            build_fieldnames(self._gt_columns, self._passthrough)
            + list(EXTENDED_EXTRA_COLUMNS)
        )
        self._file = path.open("w", newline="", encoding="utf-8-sig")
        self._writer = csv.DictWriter(self._file, fieldnames=self._fieldnames)
        self._writer.writeheader()
        self._file.flush()

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

        story_path = (
            self._run_dir / "per_component" / result.component.slug / "story.txt"
        )
        story = (
            story_path.read_text(encoding="utf-8", errors="replace")
            if story_path.is_file()
            else ""
        )
        timings = parse_story_timings(story)
        infer_s = timings.get("license")
        dl_s = timings.get("download")
        cr_s = timings.get("copyright")
        total_s = sum(v for v in (infer_s, dl_s, cr_s) if v is not None)

        row.update(
            {
                "cache_hit": "true" if result.from_cache else "false",
                "inferencer_raw_response": "",
                "license_reasoning": "",
                "inferencer_elapsed_s": f"{infer_s:.3f}" if infer_s is not None else "",
                "inferencer_cost_usd": UNKNOWN_COST if not result.from_cache else "",
                "download_attempts": " | ".join(result.download_attempts),
                "license_file_path": (
                    str(result.license_file_path) if result.license_file_path else ""
                ),
                "license_file_original_url": result.original_license_url,
                "copyright_raw_response": "",
                "copyright_reasoning": "",
                "copyright_elapsed_s": f"{cr_s:.3f}" if cr_s is not None else "",
                "copyright_cost_usd": (
                    UNKNOWN_COST
                    if (not result.from_cache and result.license_file_path is not None)
                    else ""
                ),
                "eq_license_name_reason": result.eq_license_name_reason,
                "eq_license_code_url_reason": result.eq_license_code_url_reason,
                "eq_copyright_reason": result.eq_copyright_reason,
                "eq_license_name_cost_usd": (
                    UNKNOWN_COST
                    if result.eq_license_name_reason.startswith("judge:")
                    else ""
                ),
                "eq_license_code_url_cost_usd": (
                    UNKNOWN_COST
                    if result.eq_license_code_url_reason.startswith("judge:")
                    else ""
                ),
                "eq_copyright_cost_usd": (
                    UNKNOWN_COST
                    if result.eq_copyright_reason.startswith("judge:")
                    else ""
                ),
                "grades": json.dumps(result.grades, sort_keys=True)
                if result.grades
                else "",
                "total_elapsed_s": f"{total_s:.3f}" if total_s else "",
                "total_cost_usd": UNKNOWN_COST if not result.from_cache else "",
            }
        )
        self._writer.writerow(row)
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> ExtendedWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
