"""Streaming non-audit results.csv writer."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline import ComponentResult

BASE_COLUMNS = [
    "component_name",
    "purl",
    "inferred_license_name",
    "inferred_license_code_url",
    "inferred_copyright",
]


class ResultsWriter:
    def __init__(self, path: Path, extra_columns: list[str]) -> None:
        self._path = path
        self._fieldnames = BASE_COLUMNS + list(extra_columns)
        self._file = path.open("w", newline="", encoding="utf-8-sig")
        self._writer = csv.DictWriter(self._file, fieldnames=self._fieldnames)
        self._writer.writeheader()
        self._file.flush()

    def write_row(self, result: ComponentResult) -> None:
        row = {
            "component_name": result.component.component_name,
            "purl": result.component.purl,
            "inferred_license_name": result.inferred_license_name,
            "inferred_license_code_url": result.inferred_license_code_url,
            "inferred_copyright": result.inferred_copyright,
        }
        row.update(result.component.extras)
        self._writer.writerow(row)
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> ResultsWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
