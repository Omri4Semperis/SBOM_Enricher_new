# Plan: v2 grilled requirements (dedup, enriched CSV, license layout, audit reuse, URL prompt)

**Live document.** Unlike the old design, this file is written to during
execution. The executor of phase N may edit **only two files**: its own
`P{N}_{...}.md` doc and this `PLAN.md`. It updates its row in the phase
table, reflects concise notes into its own per-phase block, and leaves
**Incoming comments** in *another* phase's block here when it discovers
something that phase must know. It never edits another phase's `P*` doc.

**Execution:** one phase per fresh session via the `complex-plan-implement-phase`
skill. Fallback without that skill: pick the lowest-numbered phase whose
**Depends on** entries are all `done` in the table below and whose own Status
is `pending`; then follow that phase doc top to bottom — its Entry criteria,
Tasks, Validation gate, Exit criteria, and On completion sections are the
complete procedure. Read this whole `PLAN.md` first for cross-phase context
and any Incoming comments left in your phase's block.

## Goal

Deliver the five requirements grilled and signed off on 2026-07-19 for the
SBOM Enricher (ADRs 0011–0015; grilling log
`docs/archive/DECISIONS_2026-07-19_grilled-requirements.md`). For the operator
this means: inputs may list the same component in many projects without the
run aborting; a new `library_approvals_enriched.csv` is the consumer-facing
deliverable; downloaded license files are organized per project; audit runs
stop leaving stray license copies; and the license-URL prompt more reliably
finds the component's own holder-bearing file. Each phase is one requirement,
end to end, proven by a pytest command.

## Context

The enricher reads an input CSV of components (`component_name`, `purl`, plus
optional ground-truth and passthrough columns), enriches each unique component
(license name, downloadable license-URL + file, copyright) via Claude + Azure
GPT-4.1, and — when GT columns are present — audits the result. See
`.cursor/skills/architecture-overview/SKILL.md` for the module map and
`docs/CONTEXT.md` for vocabulary. Requirements sources for THIS plan (do not
re-derive from anywhere else): ADRs `0011`–`0015`, `docs/CONTEXT.md`, and the
archived grilling log
`docs/archive/DECISIONS_2026-07-19_grilled-requirements.md` (detail only).

Modules every executor should know:

- `src/input_csv.py` — `read_components(path) -> list[Component]`; `Component`
  is a frozen dataclass (`component_name`, `purl`, `lib_name`, `version`,
  `slug`, `extras: dict[str,str]`). Today it **rejects any duplicate
  `component_name`** (P1 changes this).
- `src/pipeline.py` — `process_component` (enrichment spine), `apply_equality`
  (audit), `run_workers` (asyncio pool; owns the `components` list).
  `ComponentResult` carries `inferred_*`, `license_file_path`, `error`,
  `from_cache`, `is_eq_*`, `grades`.
- `src/download.py` — `fetch_license_file(...)` → `_write_license` writes
  `licenses/{slug}.ext` **and** a `per_component/{slug}/` copy.
- `src/cache.py` — `restore_license_file(record, run_dir, slug)` on cache hit.
- `src/results_csv.py` / `src/main.py` — existing `results_*.csv` +
  `_extended.csv` writers; `main.run(config)` orchestrates.
- `src/equality.py` — `compare_url_content` (re-downloads both URLs today).
- `src/prompts.py` — `license_prompt`.

Invariants that hold across all phases:

- **Bad enrichment value** = empty/whitespace, the literal `"UNKNOWN"`, or the
  component errored (`ComponentResult.error` set). There is NO "parsing error"
  sentinel — do not invent one.
- Enrichment runs **once per unique `component_name`** (ADR 0011).
- Fail-fast on conflict = raise `SystemExit` before any run dir/outputs (A6).
- `UNKNOWN` vs empty cost, cache all-or-nothing, and Story/Event-Log roles are
  unchanged by this plan.

## Phases

| Phase | Purpose | Depends on | Status | Baseline | Updated |
| - | - | - | - | - | - |
| [P1: input_dedup_conflict](./P1_input_dedup_conflict.md) | Allow duplicate names; reject only true conflicts; aggregate `project_names` | - | done | 9c0eead | 2026-07-19 |
| [P2: enriched_output_csv](./P2_enriched_output_csv.md) | Emit `library_approvals_enriched.csv` (replace/keep/append) | P1 | in progress | d666d75 | 2026-07-19 |
| [P3: license_file_layout](./P3_license_file_layout.md) | Per-project license-file layout; cache restore obeys it | P1 | pending | | |
| [P4: one_license_file](./P4_one_license_file.md) | Audit URL equality reuses inferred file; `licenses/` holds only inferred | - | pending | | |
| [P5: url_prompt_quality](./P5_url_prompt_quality.md) | Strengthen license-URL prompt (prompt-only) | - | pending | | |

Eligibility: P1, P4, P5 can start immediately. P2 and P3 wait for P1 `done`.

## Test commands

Run from the repo root (Windows / PowerShell). The in-repo venv interpreter is
authoritative.

| Purpose | Command | Expected |
| - | - | - |
| full suite | `.\.venv\Scripts\python.exe -m pytest -q` | exit 0; baseline **157 passed** (grows as phases add tests) |
| one file | `.\.venv\Scripts\python.exe -m pytest tests/test_input_csv.py -q` | exit 0, all passed |
| lint (optional) | none configured | n/a |

There is no typechecker/linter wired in this repo; "lint/typecheck" gate steps
are satisfied by the full suite passing.

## Phase notes

### P1: input_dedup_conflict

- **For other phases:** After P1, `read_components` returns **one `Component`
  per unique `component_name`** (first-seen order), not one per row. It raises
  `SystemExit` on a conflict (differing `purl` or any present GT field, under
  trim+collapse-whitespace+casefold normalization). It adds a new field
  `Component.project_names: tuple[str, ...]` — the ordered, first-seen-unique
  raw `project_name` values across that component's rows; **empty tuple when
  the input has no `project_name` column**. P3 consumes this; do not re-derive
  project sets elsewhere. Note: `project_name` also lands in `extras` (existing
  passthrough behaviour; doc-silent). P3 must consume `project_names`, not
  `extras["project_name"]`.
- **Notes:** Done. `Component.project_names: tuple[str,...]` added. Dedup loop
  in `read_components` accumulates first-seen canonical rows; conflicts raise
  `SystemExit` naming the component and field. Slug-collision check retained
  over unique names. 10 new tests; suite: 167 passed (157 baseline + 10).
  Fresh review: PASS; reviewer noted purl casefold (doc-ordered per A3) and
  `project_name` in extras (doc-silent, existing behaviour — see note above).
- **Incoming comments:**

### P2: enriched_output_csv

- **For other phases:** P2 adds `read_input_rows(path) -> tuple[list[str],
  list[dict[str,str]]]` (raw header + every row verbatim, order preserved) to
  `src/input_csv.py`, and a new `src/enriched_csv.py`. The enriched CSV is
  built post-run by joining raw rows to results by `component_name`; it is a
  read-only consumer of `ComponentResult`, so later phases changing enrichment
  values need no P2 change.
- **Notes:**
- **Incoming comments:**

### P3: license_file_layout

- **For other phases:** P3 makes `_write_license` (and cache
  `restore_license_file`) project-aware, driven by `Component.project_names`
  and a run-wide raw-name→dir map (collision suffixes). **It MUST keep the
  flat behavior — `licenses/{slug}.ext` — when no project context is passed**,
  because P4's GT download relies on flat mode. `per_component/{slug}/` stays
  flat (one dir per unique component). `ComponentResult.license_file_path`
  remains a single canonical path (first project copy, or flat).
- **Notes:**
- **Incoming comments:**
  - 2026-07-19 [from planner] P4 downloads the GT file in flat mode then
    deletes it. Do not remove or repurpose the no-project (flat) branch of
    `_write_license`.

### P4: one_license_file

- **For other phases:** P4 changes `compare_url_content` to take the inferred
  file's already-saved path/bytes instead of re-downloading it, and to delete
  the GT temp file from `licenses/` after comparison. It relies on
  `_write_license`'s flat default (see P3 note). If P3 is not yet done, P4
  still works against today's flat `licenses/`.
- **Notes:**
- **Incoming comments:**

### P5: url_prompt_quality

- **For other phases:** Prompt-only; changes `license_prompt` text in
  `src/prompts.py`. No interface change; no other phase depends on it.
- **Notes:**
- **Incoming comments:**

## On completion

Only after every phase shows `done` in the table above, in this order:

1. Graduate durable decisions out of the plan: anything in a Phase-notes
   block or a phase doc that a future maintainer must know goes to an ADR
   (invoke the `domain-modeling` skill; if unavailable, a dated note in the repo's docs).
   Note: ADRs 0011–0015 already cover A–E; confirm they still match the shipped
   code before archiving this plan.
2. Stamp the top of this file: `COMPLETED {YYYY-MM-DD} — historical record,
   not current truth`.
3. Move the whole plan directory to `docs/plans/archive/v2-grilled-requirements/`.

Stale plan docs poison future agents — archive, don't keep.
