# DECISIONS — v2 requirements grilling (enriched CSV, license files, URL quality, dedup, project layout)

Consumed: 2026-07-19 · Archived: 2026-07-19

> Spent. Embodied in ADRs 0011–0015, `docs/CONTEXT.md`, `docs/BACKLOG.md` #9,
> and the live plan `docs/plans/v2-grilled-requirements/`. (At grilling time C
> and E had no ADRs; 0014/0015 were added when this log was archived.)

Signed off by Omri. Scope: five requirements grilled to shared understanding.

ADRs: **0011** (A), **0012** (B), **0013** (D), **0014** (C), **0015** (E).
E's durable meaning is also in CONTEXT under Inferred License Code URL.

### A. Input dedup & conflict rejection — ADR 0011

- A1. Stop rejecting on duplicate `component_name`; reject only on *conflict*.
- A2. Conflict = same `component_name` with differing `purl` OR any present GT
  field (`license_name` / `license_code_url` / `copyright`). Passthrough columns
  (e.g. `project_name`) may differ freely.
- A3. Conflict comparison is aggressively normalized: trim + collapse internal
  whitespace + case-insensitive (so empty-vs-populated counts as a conflict).
- A4. Non-conflicting duplicates: first occurrence's literal values win in the
  deduped outputs.
- A5. Enrichment work runs once per unique component. `results_*.csv` +
  `_extended.csv` emit one row per unique component. The enriched CSV emits one
  row per original input row (duplicates repeated with identical enrichment,
  input order preserved).
- A6. Conflict → fail the whole run immediately, naming the component and the
  differing field. No outputs produced.

### B. Enriched output CSV (`library_approvals_enriched.csv`) — ADR 0012

- B1. New third artifact at run-dir root, fixed literal name; coexists with the
  existing `results_*.csv` + `_extended.csv`.
- B2. Contents = input columns verbatim (incl. passthrough) + the 3 enriched
  columns. No `is_eq_*`, no `inferred_*` duplicates, no extended detail.
- B3. Enriched column present in input → replace with our value, EXCEPT keep the
  original when our value is "bad": empty/whitespace, `"UNKNOWN"`, or the
  component errored.
- B4. Enriched column absent from input → add it with our value verbatim
  (including UNKNOWN/empty).
- B5. Column order: input columns keep their positions (present enriched columns
  updated in place); absent enriched columns appended after all input columns in
  canonical order `license_name, license_code_url, copyright`.
- B6. Each duplicate row shows its own literal input values (faithful
  passthrough). "First-occurrence wins" (A4) applies only to the deduped
  `results_*.csv`.
- B7. Built post-run by joining input rows to enrichment results by
  `component_name`; produced in both audit and non-audit runs.

### C. License file layout by `project_name` — ADR 0014

- C1. One project per input row; a component in N projects = N rows. Its license
  file is written under each project's directory.
- C2. `project_name` present → files live only under
  `licenses/{project}/{slug}.ext` (or `_misc`); no flat top-level copy.
  `project_name` absent → current flat `licenses/{slug}.ext`.
- C3. Blank `project_name` (while the column exists) → `licenses/_misc/{slug}.ext`.
- C4. Project split touches only `licenses/`; `per_component/{slug}/` stays flat,
  one directory per unique component.
- C5. Sanitize project names with the existing slug sanitizer; distinct raw names
  colliding to the same directory → first-seen keeps the base name, later ones
  get `(1)`, `(2)`, … suffixes.

### D. One license file per component — ADR 0013

- D1. Never re-download the inferred URL; reuse the enrichment-saved file for the
  audit comparison (no `__eq_inf` file).
- D2. Still download the GT file to compare contents, but remove it from
  `licenses/` afterward → `licenses/` holds only the inferred file per component.
- D3. `per_component/{slug}/` may keep everything (inferred + GT copies).

### E. License-URL fetch quality — ADR 0015

- E1. Prompt-only fix (no new detection code).
- E2. Strengthen the license-URL prompt: demand the component's own published
  license/copyright file (repo or package platform) naming a specific holder for
  this component; forbid canonical/boilerplate license text; include the nettle
  `.lesserv3` → `AUTHORS` worked negative example; fall back to
  AUTHORS/NOTICE/COPYRIGHT when the standard file is boilerplate. Kept
  deliberately not-too-strict (no hard "must be a repo").

### F. Cross-cutting

- F1. Conflict handling = fail-fast whole run (see A6 / ADR 0011).
- F2. Cache stays project-agnostic (keyed by `component_name`); on a hit, restore
  obeys this run's layout (C2/C3 per-project dirs / `_misc` / flat) — ADR 0014.
- F3. Slug collisions between different component names still reject (unchanged).

### Deferred / accepted residual risks (2026-07-19)

- E-risk: prompt-only has no safety net if Claude still picks boilerplate.
  Accepted → `docs/BACKLOG.md` residual risk #9. Owner: Omri — revisit if it recurs.
- D-edge: if enrichment downloaded no file but an inferred URL exists, the
  inferred side has nothing to reuse → equality stays FALSE (ADR 0013). Accepted.
