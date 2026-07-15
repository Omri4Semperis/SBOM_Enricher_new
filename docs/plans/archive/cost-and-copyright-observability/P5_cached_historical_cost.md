# P5: cached_historical_cost

**Plan:** cost-and-copyright-observability — make the enricher's spend real and
its copyright coverage complete. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** This doc is writable: record whatever detail you need here.
The other file you may edit is `PLAN.md` — your row in the phase table, a
concise reflection in your own Phase-notes block, and **Incoming comments** in
*another* phase's block when you discover something it must know. You never edit
another phase's `P*` doc. Status is tracked in `PLAN.md`'s table.

**Demo:** run with `cache_write` set — each new `cache.csv` row now carries a
`cached_historical_cost_usd` equal to that component's measured enrichment cost;
re-running with that dir as `cache_read` yields a cache hit contributing `$0`
Run Cost while the historical value persists in the cache index.

**Goal:** persist Cached Historical Cost (the LLM charges from when a cached
enrichment was originally produced) as a provenance-only column in `cache.csv`,
and expose it on `CachedRecord`. It is never added to any current-run total.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked**.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P4's Status is `done` in `PLAN.md`'s phase table
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥101 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

- **Cached Historical Cost** (`CONTEXT.md`): the LLM charges incurred when a
  cached enrichment was originally produced; provenance only, never counted as
  current-run cost. `DECISIONS.md`: "stored in new cache entries ... never
  included in the current run's totals." A cache hit incurs `$0` Run Cost
  (already true — the hit path makes no LLM call).
- `src/cache.py`: `_COLUMNS` is the 5-tuple written to `cache.csv`. `CachedRecord`
  is a frozen dataclass. `read_cache` returns `CachedRecord | None` after
  validating all three inferred fields are known and the license file exists.
  `write_cache(cache_write, component_name, result) -> bool` uses `getattr` on
  `result` and writes a full-success row only. `_load_index` uses
  `csv.DictReader` (so extra/missing columns don't crash old files).
- **Component enrichment cost** (post-P3): `combine([result.license_meta,
  result.copyright_meta]).total_usd()` — a `float | None`. Confirm the field
  names + `combine`/`total_usd` API from P1–P4 Outcomes. Equality metas are
  audit-only and NOT part of the cached enrichment (and aren't populated yet at
  `write_cache` time, which runs before `apply_equality`).
- `pricing.format_cost(float|None) -> str` yields the numeric string or
  `UNKNOWN_COST` ("unknown") — use it for the cell so a missing enrichment cost
  is `unknown`, never `$0`.
- `tests/test_cache.py` covers the current round-trip; extend it, don't rewrite.

## Files

**Touch (complete list):**

- `src/cache.py` — edit: add `cached_historical_cost_usd` to `_COLUMNS`; write it
  from the result's enrichment cost in `write_cache`; add a
  `cached_historical_cost: str` field to `CachedRecord` and populate it in
  `read_cache` (default `""`/`unknown` when the column is absent in old files).
- `tests/test_cache.py` — edit: write→read round-trip of the historical cost;
  old-index-without-column read still succeeds.

**Do not touch:** `src/pipeline.py` (`write_cache` reads the metas off `result`
via `getattr` — no pipeline edit needed), `src/summary.py`, `src/results_csv.py`,
and anything not listed. Surfacing the historical value into run outputs is out
of scope for this phase.

## Tasks

### T1: write the historical cost column

- Steps: add `"cached_historical_cost_usd"` to `_COLUMNS`. In `write_cache`,
  after the full-success guard, compute `format_cost(combine([getattr(result,
  "license_meta", CallMeta()), getattr(result, "copyright_meta", CallMeta())])
  .total_usd())` and write it into the row dict. Import `CallMeta`, `combine`,
  `format_cost` from `pricing`.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_cache.py -q` → exit 0
  (new test: a result with numeric license+copyright metas writes a numeric
  `cached_historical_cost_usd`; a result missing metas writes `unknown`).
- Commit when green.

### T2: read the historical cost back

- Steps: add `cached_historical_cost: str = ""` to `CachedRecord`; in
  `read_cache`, set it from `(row.get("cached_historical_cost_usd") or "")
  .strip()`. Do NOT let a missing/blank historical cost fail the hit (it is
  provenance, not a validity gate).
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_cache.py -q` → exit 0
  (round-trip: value written by T1 is read back on the `CachedRecord`; a cache
  index lacking the column still returns a valid `CachedRecord` with `""`). Then
  full suite (Validation gate).
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥103 passed.
2. No separate lint/typecheck gate in this repo.
3. Fresh review: `git diff {baseline from PLAN.md}..HEAD` reviewed against this
   doc plus an over-engineering lens by a context that did not implement it
   (subagent given only the diff, this doc, and the lens; if unavailable, stop
   and ask the user). Fix findings, re-run 1.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥103 passed.
- A test proves a full-success write records the component's enrichment cost in
  `cache.csv` and `read_cache` returns it on `CachedRecord.cached_historical_cost`,
  while a cache hit still makes no LLM call (existing behavior).

## Rollback

To abandon this phase: `git reset --hard {baseline hash from PLAN.md's phase
table}`, then set this phase's Status to `blocked` in `PLAN.md` with a one-line
reason in your Phase-notes block.

## Failure modes

1. Old `cache.csv` without the new column read by `read_cache` → `row.get`
   returns `None`; default to `""`. Must not crash or invalidate the hit.
2. `write_cache` computes cost before enrichment metas exist (e.g. an unexpected
   caller) → `getattr(..., CallMeta())` defaults make the cell `unknown`, not a
   crash.
3. Someone tries to add the historical value into a run total → forbidden by
   DECISIONS; it is provenance only. Keep it out of `summary.py`.

## Anti-goals

Do not, even if it seems better:

- No adding the historical cost to any current-run total or `summary.json`.
- No including equality-judge cost in the historical value (enrichment only).
- No cache schema-version / migration — DictReader tolerates the added column.
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
   confirm the new column name and `CachedRecord` field so P6's docs mention it.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: persist Cached Historical Cost as cache provenance
HEAD: a9bb85f | Branch: master
Files changed (this phase's own commit, `a9bb85f`):
- src/cache.py
- tests/test_cache.py
Commands run:
- `.\.venv\Scripts\python.exe -m pytest tests/test_cache.py -q` → exit 0, 9 passed (T1+T2 Verify)
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, 119 passed (Validation gate + Exit criteria)
- Fresh-context subagent review (diff `81e630d..HEAD` + this doc + ponytail-review lens) → PASS,
  "Lean already. Ship." One note: the diff range also contained an unrelated commit `9b7a271`
  ("markdown linting cosmetics for P4", touching only `P4_summary_run_costs_and_schema.md`) that
  landed on the branch from outside this session between baseline capture and this phase's own
  commit. Confirmed via `git show a9bb85f` that this phase's actual commit touches only
  `src/cache.py` and `tests/test_cache.py` — no scope violation.
Test status: full suite green, 119 passed (baseline entry was 115; +4 new tests in test_cache.py,
  net +4 since T1/T2 tests were added and verified together).
Assumptions:
1. `ComponentResult.license_meta`/`copyright_meta` always default to an empty (known, $0) `CallMeta`
   via `field(default_factory=CallMeta)` (confirmed in `src/pipeline.py`), so `write_cache`'s
   `getattr(..., CallMeta())` fallback is defensive-only and not exercised by any real caller today.
Open questions: none
Next action: P6 per PLAN.md's table
```
