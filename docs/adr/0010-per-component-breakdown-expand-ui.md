---
status: accepted
---

# Per-component breakdown expand UI: strip + tabs, GT vs inferred

The runtime report’s **Per-component breakdown** expand row today shows grade
chips and equality/pipeline reasons but not the actual ground-truth and
inferred values. We redesign that expand panel as **display-only** (no change
to equality, pipeline, or scoring): progressive disclosure that eventually
surfaces every per-component fact we already persist, without losing anything
the current detail view already shows.

**Always-visible strip** (on row expand): PURL (component name stays on the
table row); compact ops — download outcome, license attempts, and
per-component cost when available from the extended CSV; the three
**inferred** results (license name, license URL, copyright) each with its
grade chip. No long reasoning on the strip.

**Tabs** (v1): License name | License URL | Copyright. Default open tab =
License name. Each tab: grade; **Ground truth** | **Inferred** (side-by-side
or stacked); equality/judge reason (`eq_*_reason`); pipeline reasoning
(`license_reasoning` on name + URL tabs, `copyright_reasoning` on copyright).
URL tab also shows download outcome (and path / original URL when present).
No raw model dumps required in v1.

**Missing GT / non-audit:** strip still shows inferred values; tab shows
inferred + pipeline reasoning; GT as “—” / “no GT”; mute or hide grade chip
and equality reason when absent.

**Interaction:** multiple rows may stay expanded; section header has
**Open all** / **Close all**. Tab selection is per-row, not shared across rows.

**Data source & growth:** source of truth = the component’s
`results_*_extended.csv` row, plus `story.txt` / `meta.json` already used for
timings and reasons. Later fields land under the matching tab; leftovers go in
an **Other** tab — never dump them onto the always-visible strip. Rule: if it
is in the extended CSV or story, it must be reachable in the expand UI
eventually; omit only when truly redundant with something already shown.

**Rejected:** single-expand-only (calm but blocks compare-across-rows);
always-visible wall of GT + full reasoning (overburdens the first click).
