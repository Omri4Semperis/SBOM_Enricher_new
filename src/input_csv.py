"""Read and validate the input CSV; parse component names; build slug map."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

_SLUG_UNSAFE = re.compile(r'[\\/:*?"<>|]')


_GT_FIELDS = ("license_name", "license_code_url", "copyright")


def _norm(v: str) -> str:
    """Trim, collapse whitespace, casefold — for conflict comparison."""
    return " ".join((v or "").split()).casefold()


@dataclass(frozen=True)
class Component:
    component_name: str
    purl: str
    lib_name: str
    version: str
    slug: str
    extras: dict[str, str] = field(default_factory=dict)
    project_names: tuple[str, ...] = field(default_factory=tuple)


def make_slug(component_name: str) -> str:
    return _SLUG_UNSAFE.sub("_", component_name.strip())


def parse_component_name(component_name: str) -> tuple[str, str]:
    cleaned = component_name.strip().strip("@")
    lib_name, _, version = cleaned.rpartition("@")
    return lib_name, version


def read_input_rows(path: Path | str) -> tuple[list[str], list[dict[str, str]]]:
    """Raw header + every row verbatim (order preserved, duplicates kept)."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def read_components(path: Path | str) -> list[Component]:
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit("input CSV has no header row")
        fields = list(reader.fieldnames)
        if "component_name" not in fields or "purl" not in fields:
            raise SystemExit("input CSV must have component_name and purl columns")
        passthrough = [c for c in fields if c not in ("component_name", "purl")]
        has_project = "project_name" in fields

        # canonical_rows preserves first-seen order; project_lists tracks per-name projects
        canonical_rows: dict[str, dict[str, str]] = {}
        project_lists: dict[str, list[str]] = {}

        for row in reader:
            name = (row.get("component_name") or "").strip()
            if not name:
                raise SystemExit("empty component_name in input CSV")

            if name not in canonical_rows:
                canonical_rows[name] = row
                project_lists[name] = []
                if has_project:
                    project_lists[name].append(row.get("project_name") or "")
            else:
                canonical = canonical_rows[name]
                # Conflict check: purl
                if _norm(row.get("purl") or "") != _norm(canonical.get("purl") or ""):
                    raise SystemExit(
                        f"conflict for component {name!r}: purl differs "
                        f"({(canonical.get('purl') or '')!r} vs {(row.get('purl') or '')!r})"
                    )
                # Conflict check: present GT fields
                for gt in _GT_FIELDS:
                    if gt in fields:
                        cv = canonical.get(gt) or ""
                        rv = row.get(gt) or ""
                        if _norm(cv) != _norm(rv):
                            raise SystemExit(
                                f"conflict for component {name!r}: {gt} differs "
                                f"({cv!r} vs {rv!r})"
                            )
                # Non-conflicting duplicate: accumulate unique project names
                if has_project:
                    pn = row.get("project_name") or ""
                    if pn not in project_lists[name]:
                        project_lists[name].append(pn)

    # Slug-collision check over unique names
    slug_to_names: dict[str, list[str]] = {}
    for name in canonical_rows:
        slug = make_slug(name)
        slug_to_names.setdefault(slug, []).append(name)

    for slug, names in slug_to_names.items():
        if len(names) > 1:
            raise SystemExit(
                f"slug collision: {names!r} all sanitize to {slug!r}"
            )

    components: list[Component] = []
    for name, row in canonical_rows.items():
        purl = (row.get("purl") or "").strip()
        lib_name, version = parse_component_name(name)
        extras = {c: (row.get(c) or "") for c in passthrough}
        components.append(
            Component(
                component_name=name,
                purl=purl,
                lib_name=lib_name,
                version=version,
                slug=make_slug(name),
                extras=extras,
                project_names=tuple(project_lists[name]),
            )
        )
    return components
