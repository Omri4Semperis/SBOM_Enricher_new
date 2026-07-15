# Plan: cost-and-copyright-observability

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

Make the SBOM enricher's spend real and its copyright coverage complete. Today
`summary.json` and the extended CSV emit placeholder `unknown` costs and a
misleading `saved_by_cache_usd`, and copyright is file-extraction only. This
plan (1) captures real per-call cost/token/raw metadata from both providers,
including billable attempts later rejected by parsing; (2) rolls that up into a
reshaped `summary.json`; (3) restores the copyright fallback chain (npm author,
then Claude web); and (4) records Cached Historical Cost for provenance. The
audience is the operator reading a run's cost and coverage after the fact. All
requirements are the signed decisions in `docs/DECISIONS.md`.

## Context

- **Repo:** `C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve
  sbom-enricher agent/SBOM_Enricher_new`. Branch `master`. Python 3.13,
  stdlib-first, run as `python src/main.py` (auto-loads `configs/default.json`).
  Flat `src/` package; tests in `tests/`. No pandas (stdlib `csv`).
- **The signed contract is `docs/DECISIONS.md`.** Read it in full before any
  phase — it is the source of truth for cost semantics, the copyright
  precedence, the `summary.json` shape, and the validation rules. Vocabulary
  (Run Cost, Inference Cost, Cached Historical Cost) is in `docs/CONTEXT.md`.
- **Two live LLM providers.** Claude via local `claude` CLI subprocess
  (`src/claude_client.py`, license inference; the one configurable model).
  GPT-4.1 via fixed Azure deployment (`src/gpt41_client.py`, copyright
  extraction + equality judges). Example call shapes:
  `knowledge/query_example_claude.py`, `knowledge/query_example_gpt-4-1.py`.
- **Cost primitives already exist** in `src/pricing.py`: `MODEL_PRICING`,
  `compute_cost(model, in, out, cache_read, cache_write) -> float | None`,
  `format_cost(float|None) -> str`, and `UNKNOWN_COST = "unknown"`. Missing
  price → `None` → `unknown`, never `$0`. GPT-4.1 prices are already correct
  (input 2.00, cached 0.50, output 8.00 per 1M).
- **Old code is reference-only, never imported at runtime.** For metadata
  shapes, cite `knowledge/old_code/src/cost_tracking.py` (the `CallMeta` idea),
  `knowledge/old_code/src/client.py` (Claude CLI `total_cost_usd` + `usage`
  field names), and `knowledge/old_code/src/copyright_extractor.py` (fallback
  ladder wording). Do not port structure.
- **The metadata backbone** is introduced in P1 (`CallMeta` cost accumulator in
  `pricing.py`) and reused by every later phase. Rejected attempts are still
  billable: read cost *before* validating/parsing the payload (details in
  P1/P2). See each phase's `For other phases` note below.
- **Cache** (`src/cache.py`) is keyed on `component_name`, all-or-nothing,
  full-success-only, 5 columns today. A cache hit does zero LLM work → `$0` Run
  Cost. P5 adds provenance columns only.

## Phases

<!-- Executors update Status / Baseline / Updated for their own row only.
Status: pending | in progress | done | blocked. Baseline is the short git hash
captured at phase start. Updated is the date of the last status change. -->

| Phase                                                                   | Purpose                                                              | Depends on | Status  | Baseline | Updated |
| -                                                                       | -                                                                   | -          | -       | -        | -       |
| [P1: claude_cost_capture](./P1_claude_cost_capture.md)                  | `CallMeta` accumulator + Claude cost/raw/tokens → extended CSV       | -          | done | 27c1557 | 2026-07-15 |
| [P2: gpt41_cost_capture](./P2_gpt41_cost_capture.md)                    | GPT-4.1 cost/raw for copyright + equality judges → extended CSV      | P1         | pending |          |         |
| [P3: copyright_fallback_chain](./P3_copyright_fallback_chain.md)        | npm author → Claude web copyright fallback, cost into copyright bucket | P2       | pending |          |         |
| [P4: summary_run_costs_and_schema](./P4_summary_run_costs_and_schema.md)| Real `summary.json` cost rollup + `run_info` grouping + drop saved_by_cache | P3   | pending |          |         |
| [P5: cached_historical_cost](./P5_cached_historical_cost.md)            | Persist Cached Historical Cost in cache entries (provenance only)    | P4         | pending |          |         |
| [P6: docs_and_live_validation](./P6_docs_and_live_validation.md)        | DECISIONS/BACKLOG/archive doc fixes + live 2-call cost validation    | P5         | pending |          |         |

Filenames use `P{N}_{snake_case_title}.md`. "Depends on" lists phase ids or "-".

## Test commands

| Purpose    | Command                                   | Expected                                        |
| -          | -                                         | -                                               |
| full suite | `.\.venv\Scripts\python.exe -m pytest -q` | exit 0, ≥95 passed (baseline `e9fda4b`: 95 passed; count grows each phase) |

No separate typecheck/lint gate in this repo; the suite is the only gate.

## Phase notes

### P1: claude_cost_capture

- **For other phases:** P1 defines the shared metadata carrier in
  `src/pricing.py` — name it `CallMeta` with fields `known_usd: float`,
  `billable_calls: int`, `unknown_calls: int`, `raws: list[str]`, plus a
  `combine(metas)` (module-level, sums fields) and a `total_usd() ->
  float | None` returning `None` when `unknown_calls > 0` else `known_usd`. Every
  later phase adds each new billable LLM call's meta into the right bucket on
  `ComponentResult`. P1 adds `license_meta: CallMeta` (field) to
  `ComponentResult`. Cache hits produce an empty `CallMeta` (0 calls, 0 usd,
  known). Rejected Claude attempts: read `total_cost_usd` from the CLI JSON
  wrapper before raising `ParseFailure`.
- **Notes:** Done. `CallMeta` + `combine`/`add_call`/`total_usd`/`cost_cell` in
  `pricing.py`. `infer_license` → `(dict, CallMeta)`. Pipeline tolerates plain-dict
  fakes (empty meta). Extended CSV `inferencer_cost_usd`/`inferencer_raw_response`
  from `license_meta`. Suite: 100 passed. Deviation: touched
  `tests/test_summary.py` (assertion only; Failure mode 2).
- **Incoming comments:**

### P2: gpt41_cost_capture

- **For other phases:** P2 adds `copyright_meta: CallMeta` and
  `eq_license_name_meta` / `eq_license_code_url_meta` / `eq_copyright_meta:
  CallMeta` to `ComponentResult`, and makes `Gpt41Client.complete_json` return
  `(data, CallMeta)`. `copyright.extract_copyright` returns its meta;
  `EqResult` grows a `meta: CallMeta` field. Short-circuit equality (identical
  / normalized / no_judge) makes NO billable call → empty `CallMeta`. P3
  appends more calls into `copyright_meta`; P4 reads all five meta fields.
- **Notes:**
- **Incoming comments:**

### P3: copyright_fallback_chain

- **For other phases:** P3 makes copyright a chain: file extraction → npm
  registry `author` (npm purls only; plain HTTP, no LLM, no cost) → Claude web
  inference (billable, cost added into `copyright_meta`) → UNKNOWN, without
  overwriting an earlier success. The Claude web call reuses P1's Claude
  metadata plumbing. `copyright_meta` may now hold >1 billable call.
- **Notes:**
- **Incoming comments:**

### P4: summary_run_costs_and_schema

- **For other phases:** P4 owns `src/summary.py`. It reads the `CallMeta`
  fields on results and produces numeric buckets/total only when every
  contributing billable call is known (else `unknown`); groups the nine
  `run_info` fields; removes `saved_by_cache_usd` from `_cost_bucket` and the
  summary. `Inference Cost` = license + copyright buckets (not equality/
  preflight). Run total = enrichment + equality, excludes preflight.
- **Notes:**
- **Incoming comments:**

### P5: cached_historical_cost

- **For other phases:** P5 adds one column to `cache.csv`
  (`cached_historical_cost_usd`, provenance-only) written from the component's
  measured enrichment cost (license + copyright metas) at cache-write time, and
  exposes it on `CachedRecord`. It is never added to any current-run total.
  Cache hit stays `$0` Run Cost.
- **Notes:**
- **Incoming comments:**

### P6: docs_and_live_validation

- **For other phases:** terminal phase. Documents the now-functional cost
  output (SF1), adds the archive hash-chain note (SF2), removes BACKLOG #4/#6,
  and runs the one live minimal Claude + one live GPT-4.1 call required by
  DECISIONS. No `src/` behavior changes.
- **Notes:**
- **Incoming comments:**

## On completion

Only after every phase shows `done` in the table above, in this order:

1. Graduate durable decisions out of the plan: anything in a Phase-notes
   block or a phase doc that a future maintainer must know goes to an ADR
   (invoke the `domain-modeling` skill; if unavailable, a dated note in the repo's docs).
2. Stamp the top of this file: `COMPLETED {YYYY-MM-DD} — historical record,
   not current truth`.
3. Move the whole plan directory to `docs/plans/archive/{plan-name}/`.

Stale plan docs poison future agents — archive, don't keep.
