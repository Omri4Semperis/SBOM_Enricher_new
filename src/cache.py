"""Cross-run cache: component_name key, all-or-nothing, full-success writes only."""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

INDEX_NAME = "cache.csv"
LICENSES_SUBDIR = "licenses"
_COLUMNS = (
    "component_name",
    "inferred_license_name",
    "inferred_license_code_url",
    "inferred_copyright",
    "license_filename",
)


@dataclass(frozen=True)
class CachedRecord:
    component_name: str
    inferred_license_name: str
    inferred_license_code_url: str
    inferred_copyright: str
    license_path: Path


def _known(value: str) -> bool:
    return bool(value) and value != "UNKNOWN"


def _cache_filename(component_name: str, src: Path) -> str:
    """Unique-per-key filename (slug basename can collide across inputs)."""
    return quote(component_name, safe="@.-+") + (src.suffix or ".txt")


def _load_index(index_path: Path) -> dict[str, dict[str, str]]:
    if not index_path.is_file():
        return {}
    with index_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        key = (row.get("component_name") or "").strip()
        if key:
            out[key] = row
    return out


def _write_index(index_path: Path, rows: dict[str, dict[str, str]]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(_COLUMNS))
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow({c: rows[key].get(c, "") for c in _COLUMNS})


def read_cache(cache_read: Path | None, component_name: str) -> CachedRecord | None:
    """Return the full cached record for component_name, or None (miss / no path)."""
    if cache_read is None:
        return None
    rows = _load_index(cache_read / INDEX_NAME)
    row = rows.get(component_name)
    if row is None:
        return None
    filename = (row.get("license_filename") or "").strip()
    if not filename:
        return None
    license_path = cache_read / LICENSES_SUBDIR / filename
    if not license_path.is_file():
        return None
    name = row.get("inferred_license_name", "")
    url = row.get("inferred_license_code_url", "")
    copyright_ = row.get("inferred_copyright", "")
    if not (_known(name) and _known(url) and _known(copyright_)):
        return None
    return CachedRecord(
        component_name=component_name,
        inferred_license_name=name,
        inferred_license_code_url=url,
        inferred_copyright=copyright_,
        license_path=license_path,
    )


def write_cache(cache_write: Path | None, component_name: str, result: object) -> bool:
    """Write a full-success row + license file. Returns True if written."""
    if cache_write is None:
        return False
    path = getattr(result, "license_file_path", None)
    if not (
        _known(getattr(result, "inferred_license_name", ""))
        and _known(getattr(result, "inferred_license_code_url", ""))
        and _known(getattr(result, "inferred_copyright", ""))
        and path is not None
        and Path(path).is_file()
    ):
        return False
    src = Path(path)
    filename = _cache_filename(component_name, src)
    licenses = cache_write / LICENSES_SUBDIR
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, licenses / filename)
    index_path = cache_write / INDEX_NAME
    rows = _load_index(index_path)
    rows[component_name] = {
        "component_name": component_name,
        "inferred_license_name": result.inferred_license_name,  # type: ignore[attr-defined]
        "inferred_license_code_url": result.inferred_license_code_url,  # type: ignore[attr-defined]
        "inferred_copyright": result.inferred_copyright,  # type: ignore[attr-defined]
        "license_filename": filename,
    }
    _write_index(index_path, rows)
    return True


def restore_license_file(record: CachedRecord, run_dir: Path, slug: str) -> Path:
    """Copy cached license into run licenses/ + per_component/, return flat path."""
    ext = record.license_path.suffix or ".txt"
    body = record.license_path.read_bytes()
    licenses_dir = run_dir / "licenses"
    licenses_dir.mkdir(parents=True, exist_ok=True)
    flat = licenses_dir / f"{slug}{ext}"
    flat.write_bytes(body)
    per = run_dir / "per_component" / slug
    per.mkdir(parents=True, exist_ok=True)
    (per / flat.name).write_bytes(body)
    return flat
