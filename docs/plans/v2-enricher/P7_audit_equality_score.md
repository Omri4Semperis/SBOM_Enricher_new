# P7: audit_equality_score

**Your workspace.** This doc is writable. The other file you may edit is
`PLAN.md` — your table row, a concise Phase-notes reflection, and **Incoming
comments** in another phase's block. Never edit another phase's `P*` doc.

**Demo:** run a fixture that carries ground-truth columns — the results CSV
gains `is_eq_*` columns in the locked triplet order and a non-empty `score.csv`
tally is written.

**Goal:** Add audit mode (ADRs 0002): when ground-truth columns are present,
compare each inferred item to its ground truth, emit `TRUE`/`FALSE` `is_eq_*`
columns, and write `score.csv`. Name/copyright use the three-rung ladder; URL
equality is content sameness, not string equality. No ground-truth columns ⇒
audit mode off (unchanged from P2's non-audit output).

## Entry criteria

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P5 Status is `done` (P7 depends on P5, not P6; parallel with P6)
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed
- [ ] `git status --porcelain` → empty

## Context capsule

- P2 wrote the non-audit results CSV and column order. P5 finalized
  `Gpt41Client.complete_json(system, user) -> dict` — reuse it for the judge.
  Confirm the real signatures in P2/P5 Phase-notes.
- Audit mode is active only when one or more ground-truth columns
  (`license_name`, `license_code_url`, `copyright`) are present in the input
  (DECISIONS "Equality / comparison", CONTEXT "Audit Mode"). Detect from the
  input header.
- Locked `is_eq_*` rules:
  - Columns hold only `TRUE`/`FALSE`. An `is_eq_*` column exists only for an
    item whose ground-truth column is supplied.
  - **License name & copyright** — three-rung ladder: identical → normalized
    match (lowercase + special-char normalization, e.g. `ï¿`, `(c)`) → GPT-4.1
    judge → else FALSE. Old `license_matcher.py` / `copyright_matcher.py` show
    normalization; adapt, don't import.
  - **URL (`is_eq_license_code_url`)** — content-based (ADR 0002), not string:
    download BOTH the inferred and ground-truth URLs, compare content with the
    ladder starting at **byte identity** → normalize (whitespace/BOM/line-
    endings/case) → GPT-4.1 judge ("same license text?") → else FALSE. If the
    ground-truth URL or the inferred URL fails to download, verdict is FALSE and
    the reason (e.g. `gt_url_download_failed`) is recorded (for P8's extended
    CSV). Reuse P4's downloader for the ground-truth fetch.
- Locked judge contract (DECISIONS "LLM contract — equality judge"): one uniform
  output for all three kinds; the *prompt* varies by kind, the *shape* does not:

```json
{ "verdict": "TRUE" | "FALSE", "reasoning": "<one sentence>" }
```

  Judge always commits (no `UNKNOWN`). A failed/missing GT download resolves to
  FALSE upstream before the judge is called.

- Locked column order (DECISIONS "Main results.csv column order"): per-item
  triplet ground-truth → inferred → is_eq, sitting adjacent:

```txt
component_name, purl,
license_name,      inferred_license_name,      is_eq_license_name,
license_code_url,  inferred_license_code_url,  is_eq_license_code_url,
copyright,         inferred_copyright,         is_eq_copyright
```

  Item with no GT column collapses to just its `inferred_*` column. Extra
  passthrough input columns preserved at the end. This EXTENDS P2's writer —
  keep non-audit output identical when no GT is present.

- Locked scoring (DECISIONS "Scoring"): each graded item is `h` (hit / matches),
  `m` (mismatch / wrong value), or `u` (unknown / didn't know, didn't guess
  wrong — inferred is `UNKNOWN`). `score.csv` is a tally with a `Count` column,
  only columns for graded items, rows with `Count==0` omitted, no
  `component_name`/`purl`. Skipped entirely if no GT columns. Schema:

```txt
license_name,license_code_url,copyright,Count
h,h,h,105
h,m,u,42
```

  Per-component grades live in the extended CSV (P8), not `score.csv`.

## Files

**Touch (complete list):**

- `src/equality.py` — create: `compare_name`, `compare_copyright`,
  `compare_url_content` (each → TRUE/FALSE + reason), the shared ladder, and the
  judge call via `Gpt41Client`.
- `src/scoring.py` — create: grade one row's items → `h/m/u`; tally across rows;
  write `score.csv`.
- `src/prompts.py` — edit: add the three judge prompts (name / copyright / url).
- `src/results_csv.py` — edit: audit-aware fieldnames + row building (triplet
  order, collapse when GT absent).
- `src/pipeline.py` / `src/main.py` — edit: detect audit mode from header; after
  enrichment, run comparisons, set `is_eq_*`, grade; write `score.csv` at run
  end when audit.
- `tests/test_equality.py`, `tests/test_scoring.py`, `tests/test_results_csv.py`
  — create.

**Do not touch:** claude/gpt client internals (reuse only), cache (P6),
`summary.json`/extended CSV (P8), `knowledge/`.

## Tasks

### T1: comparison ladders

- Steps: `src/equality.py` — name/copyright ladder (identical → normalized →
  judge) and URL content ladder (download both, byte → normalize → judge,
  download-fail → FALSE + reason). Reuse P4 downloader + P5 `Gpt41Client`.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_equality.py` →
  exit 0 (identical, normalized-only, judge-decides, and GT-download-fail →
  FALSE cases; judge mocked).
- Commit when green.

### T2: scoring + score.csv

- Steps: `src/scoring.py` — grade items to `h/m/u`, tally, write `score.csv`
  (only graded columns, omit `Count==0`, skip file if no GT).
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_scoring.py` →
  exit 0 (mixed grades → correct tally rows; no GT → no file).
- Commit when green.

### T3: audit-aware results CSV + wire

- Steps: `src/results_csv.py` — fieldnames/rows in triplet order, collapse when
  GT absent, non-audit output unchanged. `src/pipeline.py`/`main.py` — detect
  audit from header, run comparisons, set `is_eq_*`, grade, write `score.csv`
  at end.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_results_csv.py
  tests/test_pipeline.py` → exit 0 (GT fixture → triplet columns + score.csv;
  non-GT fixture → 5-column output unchanged).
- Commit when green.

## Validation gate

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. Fresh review of `git diff {baseline}..HEAD` by a `generalPurpose` readonly
   subagent (diff + this doc + over-engineering lens). Fix findings, re-run 1;
   ordered-behavior findings recorded not fixed.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- Test proving GT fixture yields triplet `is_eq_*` columns + a non-empty
  `score.csv`, and a non-GT fixture is byte-identical to P2's output, passes.

## Rollback

`git reset --hard {baseline hash from PLAN.md}`, Status `blocked` + one-line
reason in Phase-notes.

## Failure modes

1. Comparing URL strings instead of content → forbidden (ADR 0002); download
   both and compare content.
2. Emitting `is_eq_*` for an item with no GT column → only graded items get
   columns.
3. Judge returning `UNKNOWN` → not allowed; it always commits TRUE/FALSE, and
   GT-download failure resolves to FALSE before the judge.

## Anti-goals

- No `component_name`/`purl` in `score.csv`.
- No consistency judge (dropped in v2), no cost/summary (P8).
- No new dependency for CSV — stdlib `csv` (matches P2).
- Nothing beyond this doc's Tasks.

## If blocked

Set Status `blocked` in `PLAN.md` (Baseline + Updated), one-line reason in
Phase-notes, report and stop.

## On completion

1. Re-check Entry/Validation/Exit.
2. `PLAN.md`: Status `done`, Baseline + Updated.
3. Reflect into Phase-notes: audit-mode detection point, `is_eq_*` field names,
   the grade/reason fields P8's extended CSV must surface, `score.csv` writer.
4. Record full **Outcome** here (same shape as P1's).

## Outcome

Objective: audit-mode `is_eq_*` ladders + score.csv (ADR 0002)
HEAD: 9007591 | Branch: master
Files changed:
- docs/plans/v2-enricher/PLAN.md
- docs/plans/v2-enricher/P7_audit_equality_score.md
- src/equality.py
- src/main.py
- src/pipeline.py
- src/prompts.py
- src/results_csv.py
- src/scoring.py
- tests/fixtures/mini_audit.csv
- tests/test_equality.py
- tests/test_pipeline.py
- tests/test_results_csv.py
- tests/test_scoring.py
Commands run:
- Entry: `pytest -q` → 58 passed; porcelain empty; baseline `e022742`
- T1: `pytest -q tests/test_equality.py` → 8 passed
- T2: `pytest -q tests/test_scoring.py` → 4 passed
- T3: `pytest -q tests/test_results_csv.py tests/test_pipeline.py` → 15 passed
- Gate: `pytest -q` → 78 passed; review PASS; post-shrink `pytest -q` → 78 passed
Test status: `.\.venv\Scripts\python.exe -m pytest -q` → 78 passed
Assumptions: none
Open questions: none
Deviations: none material (prompts added in T1 with equality; review shrinks applied)
Next action: P8 (ops_preflight_progress_summary) — depends on P6+P7, both done
