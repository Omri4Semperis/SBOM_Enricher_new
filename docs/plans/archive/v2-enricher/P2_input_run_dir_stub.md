# P2: input_run_dir_stub

**Your workspace.** This doc is writable: record whatever detail you need here.
The other file you may edit is `PLAN.md` — your row in the phase table, a
concise reflection in your own Phase-notes block, and **Incoming comments** in
another phase's block. You never edit another phase's `P*` doc. Status lives in
`PLAN.md`'s table.

**Demo:** `python src/main.py` on a tiny fixture CSV creates a run directory
with `input/` copies, `per_component/` Story files, and a
`results_{model_short}_{n}.csv` where every inferred field is `UNKNOWN`.

**Goal:** Build the runnable pipeline skeleton — validate + parse input, create
the run directory, and run a worker pool where each worker processes one
component end to end. No LLM calls yet: every stage is a stub that fills
`UNKNOWN`. This is the tracer bullet later phases hang real behavior on.

## Entry criteria

- [x] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [x] P1 Status is `done` in `PLAN.md`'s table
- [x] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed
- [x] `git status --porcelain` → empty

## Context capsule

- `src/config.py` exists (P1): `load_config(path) -> Config` with fields
  `input_file_path`, `output_base_path`, `run_name`, `model`, `workers`,
  `cache_read`, `cache_write`. Confirm the real field names in P1's Phase-notes
  block before using them.
- Locked input rules (DECISIONS "Input validation", "Identifiers & parsing"):
  - Input CSV **must** have `component_name` and `purl` columns → else
    fail-fast.
  - `component_name` column **must** have no duplicates → else fail-fast.
  - Parse `component_name`: strip whitespace, strip leading/trailing `@`, then
    `rpartition("@")` on the last `@` → `(lib_name, version)`. Example
    `awesome.me@1.0.277` → `("awesome.me", "1.0.277")`.
  - `purl` is the primary id; `lib_name`/`version` are secondary context.
  - Empty/malformed `purl` on a row does **not** fail the run.
- Locked slug rules ("Identifiers & parsing"): sanitize `component_name` for
  filesystem use by replacing `\ / : * ? " < > |` with `_` (old `make_slug`).
  Build the slug map for the whole input up front; if two distinct
  `component_name`s sanitize to the same slug → **fail-fast** listing the
  colliding raw names + shared slug. No auto-suffix.
- Locked run dir layout ("Run output layout"): under `output_base_path`,
  `{yyyymmdd_HHMMSS}_{model_short}_{n_components}/` containing:
  - `input/` — copy of the input file + copy of the run config.
  - `licenses/` — flat, one file per component (empty for now).
  - `per_component/{slug}/` — per-component dir; write a small `meta.json`
    holding raw `component_name` + `purl` (so slug→identity never lost) and the
    Story file.
  - `results_{model_short}_{n}.csv`.
  - `model_short`: mirror old `_model_name_short` (last path segment / trimmed
    model id). Confirm shape and reuse it consistently for dir + filenames.
- Locked results column order ("Main results.csv column order") — non-audit
  run (P2 has no ground truth handling yet) is exactly:
  `component_name, purl, inferred_license_name, inferred_license_code_url,
  inferred_copyright`. Extra passthrough input columns preserved at the **end**
  in original order.
- Locked CSV writer ("CSV encoding & writer"): `utf-8-sig`, stdlib
  `csv.DictWriter` with `newline=""`, stream rows as workers finish (partial
  results survive Ctrl-C). No pandas.
- Locked concurrency ("Concurrency (workers)"): one pool of size
  `config.workers`; a worker runs a component's full pipeline before taking the
  next. Old code used `asyncio`; a stub can be synchronous or `asyncio` —
  pick the simpler that still lets P3+ add `await`ed LLM calls. Prefer
  `asyncio` with a bounded worker set so P3 doesn't rewrite the pool.
- Locked Story ("Per-component story file"): plain-text human narrative per
  component. For P2 it records "stub: no inference run".
- Provide a tiny committed fixture CSV under `tests/fixtures/` (3 rows, one
  with an empty purl) — do not use the real `input/` file in tests.

## Files

**Touch (complete list):**

- `src/main.py` — create: `run(config)` entrypoint + `__main__` block loading
  `configs/default.json`; builds run dir, validates/parses input, runs the pool.
- `src/input_csv.py` — create: read + validate CSV, parse component names,
  build slug map with collision fail-fast.
- `src/run_dir.py` — create: create the run directory tree + `input/` copies +
  `model_short` / results filename helpers.
- `src/pipeline.py` — create: the per-component result object + stub
  `process_component()` (all `UNKNOWN`) + Story writer + worker pool.
- `src/results_csv.py` — create: streaming `DictWriter` for non-audit columns.
- `tests/fixtures/mini.csv` — create: 3-row fixture.
- `tests/test_input_csv.py`, `tests/test_run_dir.py`, `tests/test_pipeline.py`
  — create: tests for validation, slug collision, dir layout, stub run output.

**Do not touch:** `src/config.py` (import only), `configs/default.json`,
`knowledge/`, the real `input/` data.

## Tasks

### T1: input parsing + validation

- Steps: `src/input_csv.py` — `read_components(path) -> list[Component]` where
  `Component` carries raw `component_name`, `purl`, parsed `lib_name`,
  `version`, `slug`. Fail-fast (`SystemExit`) on missing columns, duplicate
  `component_name`, slug collision.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_input_csv.py` →
  exit 0. Include a collision test (two names → same slug) asserting
  `SystemExit`.
- Commit when green.

### T2: run directory

- Steps: `src/run_dir.py` — `create_run_dir(config, components) -> Path`
  building the locked tree, copying input file + config into `input/`, creating
  `licenses/` and `per_component/{slug}/meta.json`. Add `model_short` +
  results-filename helpers.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_run_dir.py` →
  exit 0 (asserts dir names, `input/` copies, `meta.json` content).
- Commit when green.

### T3: stub pipeline + results CSV + wire main

- Steps: `src/pipeline.py` — result object with `inferred_license_name`,
  `inferred_license_code_url`, `inferred_copyright` (all default `"UNKNOWN"`),
  stub `process_component`, Story writer, worker pool of size `config.workers`.
  `src/results_csv.py` — streaming `DictWriter` (`utf-8-sig`, non-audit column
  order). `src/main.py` — wire it all: load config → read components → create
  run dir → run pool → stream rows.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_pipeline.py` →
  exit 0 (runs `run()` on `mini.csv`, asserts results CSV has 3 rows all
  `UNKNOWN`, a Story per component).
- Commit when green.

## Validation gate

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. Fresh review: `git diff {baseline}..HEAD` reviewed against this doc + an
   over-engineering lens by a `generalPurpose` readonly subagent (diff + this
   doc + lens only). Fix findings, re-run 1; ordered-behavior findings are
   recorded, not fixed.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- `.\.venv\Scripts\python.exe src\main.py` after pointing `input_file_path` at
  `tests/fixtures/mini.csv` (via a temp config or env — do not edit
  `default.json`) → a run dir with the 5-column results CSV, all `UNKNOWN`.

## Rollback

`git reset --hard {baseline hash from PLAN.md}`, set Status `blocked` with a
one-line reason in your Phase-notes block.

## Failure modes

1. Worker pool design fights P3's async LLM calls → choose `asyncio` now with a
   bounded set/semaphore so P3 adds `await` without a rewrite.
2. Column order drifts from the locked spec → copy the exact non-audit column
   list from the capsule; audit columns are P7's job, not now.
3. Writing partial results only at the end → stream per row so Ctrl-C keeps
   finished rows (locked requirement).

## Anti-goals

- No LLM calls, no download, no cache, no audit/`is_eq_*`/`score.csv` — later
  phases. Every inferred field stays `UNKNOWN`.
- No `summary.json` / extended CSV / progress bar — P8.
- No console prompts (old `console_input.py`) — config is file-driven.
- Nothing beyond this doc's Tasks.

## If blocked

Set Status `blocked` in `PLAN.md` (fill Baseline + Updated), add a one-line
reason to your Phase-notes block, report to the user and stop.

## On completion

1. Re-check every Entry/Validation/Exit item.
2. In `PLAN.md`: Status `done`, fill Baseline + Updated.
3. Reflect into this phase's Phase-notes block the real signatures other phases
   need: the result object fields/type, `process_component` signature, worker
   pool entry point, Story-append helper, `model_short` helper.
4. Record full outcome here under **Outcome** (same shape as P1's).

## Deviations

1. `create_run_dir(config, components)` has no config-file path, so
   `input/config.json` is a JSON snapshot of the resolved `Config` fields
   (not a byte-copy of the caller's config file).
2. `main.py` accepts an optional config-path argv (default
   `configs/default.json`) so Exit criteria can use a temp config without
   editing `default.json`.
3. Exit demo left untracked `runs/` — `.gitignore` was outside Touch; flagged
   to P8 via Incoming comment.

## Outcome

Objective: CSV validate/parse + run dir + stub asyncio worker pipeline
HEAD: bd73882 | Branch: master
Files changed:

- docs/plans/v2-enricher/PLAN.md
- docs/plans/v2-enricher/P2_input_run_dir_stub.md
- src/input_csv.py
- src/main.py
- src/pipeline.py
- src/results_csv.py
- src/run_dir.py
- tests/fixtures/mini.csv
- tests/test_input_csv.py
- tests/test_pipeline.py
- tests/test_run_dir.py
Commands run:
- Entry: `pytest -q` → 6 passed; porcelain empty; baseline `f65cd87`
- T1: `pytest -q tests/test_input_csv.py` → 5 passed
- T2: `pytest -q tests/test_run_dir.py` → 3 passed
- T3/gate: `pytest -q` → 15 passed
- Exit: `python src\main.py <temp config→mini.csv>` → run dir with
  `results_ClaudeOpu-4-8_3.csv`, all inferred fields `UNKNOWN`
- Fresh review (readonly subagent on `git diff f65cd87..HEAD`) → PASS, lean
Test status: `.\.venv\Scripts\python.exe -m pytest -q` → 15 passed
Assumptions: Story filename is `story.txt` (DECISIONS did not name the file)
Open questions: none
Next action: P3 (license_inference)
