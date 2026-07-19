---
status: accepted
---

# License files are laid out under `licenses/{project}/` when `project_name` is present

When the input has a `project_name` column, each component's downloaded license
file is written under every project it belongs to — `licenses/{project}/{slug}.ext`
(blank cell → `_misc`; no flat top-level copy). When the column is absent, the
layout stays flat (`licenses/{slug}.ext`). `per_component/{slug}/` stays flat
either way. Project directory names use the existing slug sanitizer; distinct
raw names that collide get `(1)`, `(2)`, … suffixes (first-seen keeps the base).
Cache stays keyed by `component_name`; on a hit, restore obeys this run's layout.

**Rejected:** always-flat licenses (previous behavior) — multi-project inputs need
per-project deliverable trees. Splitting `per_component/` by project — wastes
space and breaks the one-dir-per-unique-component Story/meta convention.
Keying the cache by project — would re-enrich the same component per project.
