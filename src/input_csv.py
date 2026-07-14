"""Read and validate the input CSV; parse component names; build slug map."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

_SLUG_UNSAFE = re.compile(r'[\\/:*?"<>|]')


@dataclass(frozen=True)
class Component:
    component_name: str
    purl: str
    lib_name: str
    version: str
    slug: str
    extras: dict[str, str] = field(default_factory=dict)


def make_slug(component_name: str) -> str:
    return _SLUG_UNSAFE.sub("_", component_name.strip())


def parse_component_name(component_name: str) -> tuple[str, str]:
    cleaned = component_name.strip().strip("@")
    lib_name, _, version = cleaned.rpartition("@")
    return lib_name, version


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

        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for row in reader:
            name = (row.get("component_name") or "").strip()
            if not name:
                raise SystemExit("empty component_name in input CSV")
            if name in seen:
                raise SystemExit(f"duplicate component_name: {name!r}")
            seen.add(name)
            rows.append(row)

    slug_to_names: dict[str, list[str]] = {}
    for row in rows:
        name = (row.get("component_name") or "").strip()
        slug = make_slug(name)
        slug_to_names.setdefault(slug, []).append(name)

    for slug, names in slug_to_names.items():
        if len(names) > 1:
            raise SystemExit(
                f"slug collision: {names!r} all sanitize to {slug!r}"
            )

    components: list[Component] = []
    for row in rows:
        name = (row.get("component_name") or "").strip()
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
            )
        )
    return components
