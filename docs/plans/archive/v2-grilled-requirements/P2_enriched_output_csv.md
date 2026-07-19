# P2: enriched_output_csv

**Plan:** v2 grilled requirements — deliver the five 2026-07-19 signed-off
requirements for the SBOM Enricher. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** Write freely here during implementation. Your only other
editable file is `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other phases' blocks); never another phase's `P*` doc.

**Demo:** after a run, the run dir contains `library_approvals_enriched.csv`
with exactly one row per original input row (duplicates repeated), our three
enrichment values written into the license/URL/copyright columns, keeping the
original cell wherever our value is bad.

**Goal:** Implement requirement B / ADR 0012. Add a new deliverable,
`library_approvals_enriched.csv`, at the run-dir root, produced post-run in
both audit and non-audit runs by joining the raw input rows to enrichment
results by `component_name`. Columns present in the input are overwritten with
our value (original kept when ours is bad); absent columns are appended.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] P1 Status is `done` in `PLAN.md`'s phase table (this phase needs its dedup + one-result-per-name guarantee)
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥157 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

Requirement B (from ADR 0012; detail in
`docs/archive/DECISIONS_2026-07-19_grilled-requirements.md` §B):

- B1: new third artifact at the run-dir root, fixed literal name
  `library_approvals_enriched.csv`; coexists with `results_*.csv` +
  `_extended.csv`.
- B2: contents = input columns verbatim (incl. passthrough) + the 3 enriched
  columns. No `is_eq_*`, no `inferred_*` names, no extended detail.
- B3: an enriched column **present** in the input → replace with our value,
  EXCEPT keep the original cell when our value is **bad** (empty/whitespace,
  `"UNKNOWN"`, or the component errored).
- B4: an enriched column **absent** from the input → add it with our value
  verbatim (including `UNKNOWN`/empty).
- B5: column order — input columns keep their positions (a present enriched
  column is updated in place); absent enriched columns are appended after all
  input columns in the canonical order `license_name, license_code_url,
  copyright`.
- B6: each duplicate row shows its OWN literal input values (faithful
  passthrough). "First-occurrence wins" (A4) is a `results_*.csv` rule only and
  does NOT apply here.
- B7: built post-run by joining input rows to results by `component_name`;
  produced in BOTH audit and non-audit runs.

The three enriched columns map to `ComponentResult` fields:

- `license_name` ← `result.inferred_license_name`
- `license_code_url` ← `result.inferred_license_code_url`
- `copyright` ← `result.inferred_copyright`

Bad-value rule (shared plan invariant): a value is bad when, after `strip()`,
it is empty, equals `"UNKNOWN"`, or `result.error` is non-empty (component
errored). When bad AND the column exists in the input → keep the original cell.
When the column is absent → always write our value verbatim (B4), even if bad.

Where things live now:

- `src/input_csv.py` — has the CSV-reading idiom (`utf-8-sig`,
  `csv.DictReader`). After P1, `read_components` returns unique components. Add
  a separate raw-row reader here (see T1) — it re-reads the file; the input CSV
  is small, a second read is fine and keeps the two concerns separate.
- `src/main.py` — `run(config)` computes `out = create_run_dir(...)`, runs
  workers to get `results: list[ComponentResult]`, then writes `score.csv`
  (audit only), `summary.json`, `runtime_report.html`. Add the enriched-CSV
  write after workers complete and before/after summary — anywhere post-`results`
  is fine; put it right after the `results` are in hand.
- `ComponentResult.component.component_name` is the join key.

Join semantics: build `by_name = {r.component.component_name: r for r in
results}`. For each raw input row, look up by its stripped `component_name`
(the same strip P1 applied). Every row matches exactly one result (P1
guarantees one result per unique name and rejects conflicts). If a lookup
misses, that's a real bug — raise, don't silently blank.

Gotcha: write with `newline=""` and `encoding="utf-8-sig"` to match the other
CSV writers. Preserve the raw header order from the input for the input
columns; append absent enriched columns after them in canonical order.

## Files

**Touch (complete list):**

- `src/input_csv.py` — edit: add `read_input_rows(path) -> tuple[list[str],
  list[dict[str,str]]]` returning `(fieldnames, rows)` verbatim (order
  preserved, duplicates kept). Do NOT touch `read_components` again.
- `src/enriched_csv.py` — create: the join + replace/keep/append writer.
- `src/main.py` — edit: call the writer after `results` are available, writing
  `out / "library_approvals_enriched.csv"`.
- `tests/test_enriched_csv.py` — create: unit-test the writer against crafted
  rows + fake `ComponentResult`s.

**Do not touch:** `src/results_csv.py` (the audit view is separate — B2),
`src/pipeline.py`, and anything not listed under Touch. Needing an unlisted
file means the plan is wrong: record it as a note here and a comment in your
`PLAN.md` block; if the phase can't proceed without it, follow **If blocked**.

## Tasks

### T1: raw-row reader

- Steps: in `src/input_csv.py` add `read_input_rows(path)`: open with
  `encoding="utf-8-sig"`, `csv.DictReader`; return
  `(list(reader.fieldnames), [dict(row) for row in reader])`. No validation
  beyond what `read_components` already enforced earlier in the run (it runs
  first and raises on bad input). Preserve order and duplicates.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_input_csv.py -q`
  → exit 0 (existing tests still pass; new reader compiles).
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: enriched CSV writer

- Steps: in `src/enriched_csv.py` add a pure function, e.g.
  `write_enriched_csv(path, fieldnames, rows, results)`:
  - `ENRICHED = ("license_name", "license_code_url", "copyright")` mapping to
    the three `inferred_*` fields.
  - `by_name = {r.component.component_name: r for r in results}`.
  - Output header = input `fieldnames` in order, then each enriched column NOT
    already in `fieldnames`, appended in canonical order.
  - For each input row: copy the row verbatim; look up its result by stripped
    `component_name` (raise `KeyError`/`SystemExit` on a miss). For each
    enriched column: compute `ours` = the matching `inferred_*`; `bad` =
    `ours.strip()` empty or `== "UNKNOWN"` or `result.error`. If the column is
    in `fieldnames` (present): write `ours` unless `bad` (then keep the row's
    original cell). If absent: always write `ours`.
  - Write with `newline=""`, `encoding="utf-8-sig"`; header row then data rows.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_enriched_csv.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T3: wire into the run + tests

- Steps:
  - In `src/main.py`, after `results` are collected (post-`run_workers`), call
    `read_input_rows(config.input_file_path)` and
    `write_enriched_csv(out / "library_approvals_enriched.csv", fieldnames,
    rows, results)`. Do this unconditionally (audit AND non-audit — B7).
  - In `tests/test_enriched_csv.py`, cover: present column overwritten with a
    good value; present column KEPT when ours is empty / `UNKNOWN` / errored
    (B3, all three); absent column appended verbatim incl. `UNKNOWN` (B4);
    duplicate input rows each repeated with identical enrichment and their own
    literal passthrough (B6); column order — present in place, absent appended
    canonical (B5). Use lightweight fake result objects exposing
    `component.component_name`, `inferred_*`, and `error`.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥ (prior
  baseline + new tests) passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed (no
   regressions; new tests included).
2. No separate typecheck/lint in this repo — step 1 covers it.
3. Fresh review: the diff `git diff {baseline}..HEAD` (baseline from `PLAN.md`)
   is reviewed against this doc plus an over-engineering lens by a context that
   did not implement it (subagent given only the diff, this doc, and the lens;
   if unavailable, stop and ask the user to review in a new session). Fix
   findings, re-run 1 — but a lens finding on something this doc explicitly
   ordered (e.g. the second CSV read) is NOT fixed; record it as a note here
   and, if it affects another phase, an Incoming comment in that phase's block.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_enriched_csv.py -q` → exit
  0, all passed (present-replace, keep-on-bad ×3, absent-append, duplicate-row,
  column-order).
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.

## Anti-goals

Do not, even if it seems better:

- No `is_eq_*`, `inferred_*`, or extended columns in this file — that's
  `results_*.csv` / `_extended.csv` (B2).
- No first-occurrence-wins here — every input row is faithful (B6).
- No changes to enrichment or to `ComponentResult`; this is a read-only
  consumer built post-run.
- No new dependency; use stdlib `csv`.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list, do not edit another
phase's doc. To abandon work already done, roll back with
`git reset --hard {baseline hash from PLAN.md's phase table}`.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (the start
   hash) and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block
   (confirm the artifact name + that it's produced in both run modes). Keep it
   short; write the full detail below and point to it.
4. Record the full outcome in this doc under an **Outcome** heading:

## Outcome
Objective: Emit `library_approvals_enriched.csv` via post-run join (replace/keep/append).
HEAD: 18e53b1 | Branch: master
Files changed:
- docs/plans/v2-grilled-requirements/PLAN.md
- src/enriched_csv.py
- src/input_csv.py
- src/main.py
- tests/test_enriched_csv.py
Commands run:
- Entry: `pytest -q` → 167 passed; clean tree
- T1 Verify: `pytest tests/test_input_csv.py -q` → 15 passed
- T2 Verify: `pytest tests/test_enriched_csv.py -q` → 8 passed
- T3/gate: `pytest -q` → 175 passed
- Exit: `pytest tests/test_enriched_csv.py -q` → 8 passed; `pytest -q` → 175 passed
- Fresh review (subagent on `git diff d666d75..HEAD`): PASS, no findings
Test status: `.\.venv\Scripts\python.exe -m pytest -q` → 175 passed
Assumptions: none
Open questions: none
Next action: P3 (license_file_layout) or P4 (one_license_file) or P5 (url_prompt_quality) — all eligible (P3 needs P1 done ✓)
