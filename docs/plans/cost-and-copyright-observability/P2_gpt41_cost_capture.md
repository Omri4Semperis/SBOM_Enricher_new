# P2: gpt41_cost_capture

**Plan:** cost-and-copyright-observability — make the enricher's spend real and
its copyright coverage complete. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** This doc is writable: record whatever detail you need here.
The other file you may edit is `PLAN.md` — your row in the phase table, a
concise reflection in your own Phase-notes block, and **Incoming comments** in
*another* phase's block when you discover something it must know. You never edit
another phase's `P*` doc. Status is tracked in `PLAN.md`'s table.

**Demo:** run the fixture test and see `copyright_cost_usd` and the three
`eq_*_cost_usd` cells in `results_*_extended.csv` show real numbers computed
from GPT-4.1 token usage, and `copyright_raw_response` populated — instead of
`unknown` / empty.

**Goal:** make `Gpt41Client.complete_json` return a `CallMeta` (cost from
`response.usage` via `pricing.compute_cost`, raw content, for every billable
attempt including parse-rejected ones), propagate it through
`copyright.extract_copyright` and the three equality judges, store it on
`ComponentResult`, and surface the copyright + equality costs and copyright raw
into the extended CSV.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked**.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P1's Status is `done` in `PLAN.md`'s phase table
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥96 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

- `CallMeta` lives in `src/pricing.py` (P1) — reuse exactly; confirm field
  names/methods from P1's Outcome. `add_call(cost_usd, raw)` records one attempt;
  `total_usd()` / `cost_cell()` summarize.
- `src/gpt41_client.py`: `Gpt41Client.complete_json(system, user) -> dict`.
  `once()` calls `create(...)` then `_parse_json_content(content)`; retries via
  `with_retries`. **Usage shape** (`knowledge/old_code/src/gpt41_client.py:80-93`):
  `response.usage.prompt_tokens`, `.completion_tokens`; optional cached tokens at
  `response.usage.prompt_tokens_details.cached_tokens`. Cost =
  `compute_cost("gpt-4.1", in, out, cache_read)`. Billed even when content fails
  parse → record meta before raising `ParseFailure`.
- `src/copyright.py`: `extract_copyright(license_text) -> dict` (`copyright`,
  `reasoning`); calls `complete_json`. Empty text / exhausted / placeholder →
  UNKNOWN with no or partial meta. Return the meta with the dict.
- `src/equality.py`: `EqResult(verdict, reason)` frozen. `_judge(client, system,
  user)` is the only GPT call; `_text_ladder` short-circuits on `identical` /
  `normalized` / `no_judge` (NO call → empty meta). `compare_name` /
  `compare_copyright` / `compare_url_content` wrap it. Add `meta: CallMeta`.
- `src/pipeline.py`: `apply_equality` stores `eq.reason`; `process_component`
  calls `extract_copyright(text)` (~line 117). Cache hits skip both (empty metas).
- `src/results_csv.py`: `copyright_raw_response`, `copyright_cost_usd`, and the
  three `eq_*_cost_usd` cells are placeholder, driven by
  `reason.startswith("judge:")` — replace with the stored metas.
- `tests/test_copyright.py` fakes `complete_json` with a plain dict — its
  contract becomes `(dict, CallMeta)`; update the fakes.

## Files

**Touch (complete list):**

- `src/gpt41_client.py` — edit: `complete_json` returns `(dict, CallMeta)`;
  record usage-based cost + raw per attempt.
- `src/copyright.py` — edit: return meta; thread through all UNKNOWN branches.
- `src/equality.py` — edit: add `meta: CallMeta` to `EqResult`; `_judge` fills
  it; short-circuits use an empty `CallMeta`.
- `src/pipeline.py` — edit: add `copyright_meta`, `eq_license_name_meta`,
  `eq_license_code_url_meta`, `eq_copyright_meta: CallMeta` to `ComponentResult`;
  store from the calls.
- `src/results_csv.py` — edit: fill copyright + eq cost cells and copyright raw
  from the metas.
- `tests/test_copyright.py` — edit: fakes return `(dict, CallMeta)`; assert cost.
- `tests/test_equality.py` — edit: judge path carries numeric meta; short-circuit
  path carries empty meta.
- `tests/test_results_csv.py` — edit: extended row shows numeric copyright/eq cost.

**Do not touch:** `src/summary.py` (P4 owns the run-level rollup),
`src/claude_client.py`, `src/pricing.py` (reuse only), and anything not listed.

## Tasks

### T1: gpt41_client returns CallMeta

- Steps: in `once()`, after a successful `create(...)`, build a `CallMeta` and
  `add_call(cost_usd=compute_cost("gpt-4.1", prompt_tokens, completion_tokens,
  cached_tokens), raw=content)` **before** `_parse_json_content` — so a
  `ParseFailure` still records the billed attempt. Transport errors
  (`APIConnectionError` etc.) record nothing. Accumulate across retries and
  return `(data, meta)` from `complete_json`. Read tokens defensively
  (`getattr`, `response.usage or None`) → missing usage means `cost_usd=None`
  (unknown).
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -q` →
  exit 0 after fakes updated (fakes now return `(dict, CallMeta)`).
- Commit when green.

### T2: thread meta through copyright + equality

- Steps: `extract_copyright` returns `(dict, CallMeta)`; every UNKNOWN early
  return supplies the meta it has (empty `CallMeta` when no call was made, e.g.
  empty license text). In `equality.py` add `meta: CallMeta` to `EqResult`
  (default empty); `_judge` returns `EqResult(..., meta=meta)` from the
  `complete_json` call; `_text_ladder` short-circuit returns keep the default
  empty meta.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_equality.py
  tests/test_copyright.py -q` → exit 0 (new asserts: judge verdict carries a
  billable meta; `identical`/`normalized`/`no_judge` carry 0 billable calls).
- Commit when green.

### T3: store metas on result + write to extended CSV

- Steps: add the four `CallMeta` fields to `ComponentResult`; in
  `process_component` store `copyright_meta` from `extract_copyright`; in
  `apply_equality` store each `eq.meta` into the matching field. In
  `results_csv.py` replace the four placeholder cost cells with `.cost_cell()`
  (empty string when `from_cache` or when the meta made no billable call), and
  `copyright_raw_response` with `"\n---\n".join(result.copyright_meta.raws)`.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_results_csv.py
  tests/test_pipeline.py -q` → exit 0. Then full suite (Validation gate).
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥98 passed.
2. No separate lint/typecheck gate in this repo.
3. Fresh review: `git diff {baseline from PLAN.md}..HEAD` reviewed against this
   doc plus an over-engineering lens by a context that did not implement it (a
   subagent given only the diff, this doc, and the lens; if unavailable, stop
   and ask the user). Fix findings, re-run 1. A finding on capturing raw of
   rejected attempts is NOT fixed; record it as a note.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥98 passed.
- A test asserts the extended CSV `copyright_cost_usd` is numeric after a mocked
  GPT-4.1 copyright call with usage, and a judged equality row shows a numeric
  `eq_*_cost_usd` while a normalized-match row shows an empty one.

## Rollback

To abandon this phase: `git reset --hard {baseline hash from PLAN.md's phase
table}`, then set this phase's Status to `blocked` in `PLAN.md` with a one-line
reason in your Phase-notes block.

## Failure modes

1. `response.usage is None` (some deployments omit it) → `cost_usd=None` →
   `unknown` cell. Correct behavior; do not fabricate `$0`.
2. `cached_tokens` attribute path missing → `getattr(..., 0)`; never crash on a
   missing optional field.
3. `EqResult` is frozen and compared in tests → adding a field with a default
   keeps existing constructions valid; check `tests/test_scoring.py` /
   `grade_row` still pass (they read `verdict`/`reason`, not `meta`).

## Anti-goals

Do not, even if it seems better:

- No touching `src/summary.py` — P4 owns the run-level rollup.
- No copyright fallbacks here — P3 owns the npm/web chain.
- No new per-call JSON artifact — raws live in the CSV column (joined).
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here"
  fixes. Spare capacity goes into verification, not scope.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list, do not edit another
phase's doc.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set Status `done`, fill Baseline + Updated.
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block —
   confirm the five `CallMeta` field names on `ComponentResult` and the
   `complete_json` / `extract_copyright` / `EqResult` return shapes so P3–P5
   rely on the real signatures.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: capture GPT-4.1 copyright + equality cost/raw on results + CSV
HEAD: {git rev-parse --short HEAD} | Branch: {git branch --show-current}
Files changed: {git diff --name-only <baseline>..HEAD output}
Commands run: {the Verify/gate commands and their observed results}
Test status: {suite command + observed result}
Assumptions: {numbered, or "none"}
Open questions: {numbered, or "none"}
Next action: P3 per PLAN.md's table
```

## Outcome

Objective: capture GPT-4.1 copyright + equality cost/raw on results + CSV

HEAD: 1ceda36 | Branch: master

Files changed:
- docs/plans/cost-and-copyright-observability/PLAN.md
- src/copyright.py
- src/equality.py
- src/gpt41_client.py
- src/pipeline.py
- src/results_csv.py
- tests/test_copyright.py
- tests/test_equality.py
- tests/test_results_csv.py

Commands run:
- Entry: `pytest -q` → 100 passed; `git status --porcelain` → empty; baseline `462e80a`
- T1 Verify: `pytest tests/test_copyright.py -q` → 6 passed
- T2 Verify: `pytest tests/test_equality.py tests/test_copyright.py -q` → 15 passed
- T3 Verify: `pytest tests/test_results_csv.py tests/test_pipeline.py -q` → 17 passed
- Validation gate: `pytest -q` → 102 then 103 passed after review fix
- Fresh review: Task subagent on `git diff 462e80a..HEAD` vs this doc + ponytail lens

Test status: `.\.venv\Scripts\python.exe -m pytest -q` → 103 passed

Assumptions:
1. Pipeline keeps plain-dict `extract_copyright` fake tolerance (same as P1 license), because `tests/test_pipeline.py` / `tests/test_summary.py` are outside Touch.
2. Attaching accumulated `CallMeta` as `exc.meta` on `complete_json` raise is the minimal way to give copyright fail-closed the partial meta the capsule requires.

Open questions: none

Deviations / review notes:
1. After successful `create`, `add_call` runs even when `choices` is empty/malformed (review must-fix) — then `ParseFailure`.
2. Over-engineering note (not fixed — lens must not override Touch/P1 pattern): dual tuple|dict unpack in `process_component` for stale fakes; planner may later update fakes and unpack unconditionally.

Signatures for later phases:
- `Gpt41Client.complete_json(...) -> tuple[dict, CallMeta]` (on raise: `exc.meta`)
- `extract_copyright(...) -> tuple[dict, CallMeta]`
- `EqResult(verdict, reason, meta=CallMeta())`
- `ComponentResult`: `license_meta`, `copyright_meta`, `eq_license_name_meta`, `eq_license_code_url_meta`, `eq_copyright_meta`

Next action: P3 per PLAN.md's table
