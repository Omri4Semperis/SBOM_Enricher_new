# P4: summary_run_costs_and_schema

**Plan:** cost-and-copyright-observability — make the enricher's spend real and
its copyright coverage complete. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** This doc is writable: record whatever detail you need here.
The other file you may edit is `PLAN.md` — your row in the phase table, a
concise reflection in your own Phase-notes block, and **Incoming comments** in
*another* phase's block when you discover something it must know. You never edit
another phase's `P*` doc. Status is tracked in `PLAN.md`'s table.

**Demo:** open a new run's `summary.json` — the nine run fields are nested under
`run_info`, `costs.total_usd` is a real number (or `unknown` if any billable
call had unknown cost), each bucket's `total_usd`/`unknown_cost_calls` reflects
the captured `CallMeta`, and `saved_by_cache_usd` appears nowhere.

**Goal:** replace `summary.py`'s placeholder cost logic with a real rollup of
the `CallMeta` fields captured in P1–P3, reshape the payload to nest `run_info`,
and remove `saved_by_cache_usd` entirely.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked**.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P3's Status is `done` in `PLAN.md`'s phase table
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥101 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

- `src/summary.py::build_summary(config, run_dir, results, *, started_at,
  ended_at, wall_seconds) -> dict` currently hard-codes every bucket to
  `total_usd=None` (unknown) and derives `unknown_cost_calls` by re-deriving
  from `from_cache` / `reason.startswith("judge:")`. Replace that derivation
  with the real `CallMeta` on each result (P1–P3 populate them).
- **`ComponentResult` cost fields (post-P3), confirm names from Outcomes:**
  `license_meta`, `copyright_meta`, `eq_license_name_meta`,
  `eq_license_code_url_meta`, `eq_copyright_meta` — all `CallMeta`.
- **`CallMeta` API (P1):** `known_usd`, `billable_calls`, `unknown_calls`,
  `raws`; `total_usd() -> float | None`; module-level `combine(metas)`.
- `_cost_bucket(*, total_usd, n, unknown_calls, saved_by_cache_usd=0.0,
  include_saved=True)` builds one bucket dict. **Remove** the
  `saved_by_cache_usd` param and the `include_saved` branch entirely.
- **Signed target shape** (`DECISIONS.md` "Output contract"): `run_info` holds,
  in this exact order, `run_dir, run_id, run_name, model, workers, components,
  cache_hits, started_at_utc, ended_at_utc`. These are NOT duplicated at the top
  level. `costs` and `timings` stay top-level objects.
- **Cost semantics** (`DECISIONS.md`): a bucket's `total_usd` and the run total
  are numeric only when every contributing billable call is known; else
  `unknown`. Run total = enrichment (license + copyright) + equality judges;
  excludes connectivity preflight (never captured here anyway). A cache hit
  contributes `$0` (empty `CallMeta`).
- Consumers of the shape: `src/main.py` only writes the dict (no field access).
  `tests/test_summary.py` asserts top-level `run_name`/`model`/`workers`/
  `components`/`started_at_utc` and `costs`/`timings` — these move under
  `run_info` and MUST be updated in this phase. `timings` block is unchanged.

## Files

**Touch (complete list):**

- `src/summary.py` — edit: real `CallMeta` rollup; nest `run_info`; drop
  `saved_by_cache_usd`.
- `tests/test_summary.py` — edit: assert `run_info` nesting, numeric bucket +
  run totals from populated metas, `unknown` when a meta has `unknown_calls`,
  and that no `saved_by_cache_usd` key exists anywhere.

**Do not touch:** `src/main.py` (it only passes the dict through — verify, don't
edit), `src/results_csv.py`, `src/pricing.py` (reuse only), and anything not
listed. If `main.py` genuinely needs a change, that means the plan is wrong —
follow **If blocked**.

## Tasks

### T1: roll up real costs per bucket + run total

- Steps: in `build_summary`, for each bucket `combine` the matching `CallMeta`
  across results (license → `license_meta`; copyright → `copyright_meta`;
  equality license/url/copyright → the three `eq_*_meta`). Build each bucket
  from `combined.total_usd()` and `combined.unknown_calls`. Compute the run
  total by `combine`-ing all five combined metas (or all per-result metas) →
  `total_usd`/`avg_per_row_usd` numeric only when `unknown_calls == 0`. Remove
  the old `infer_unknown` / `copyright_unknown` / `eq_*_unknown` derivations.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_summary.py -q` →
  exit 0 after test updates (a result with a numeric `license_meta` → numeric
  `license_inference.total_usd`; a result whose meta has `unknown_calls>0` →
  bucket + run total `unknown`).
- Commit when green.

### T2: drop saved_by_cache_usd and nest run_info

- Steps: delete the `saved_by_cache_usd` param + `include_saved` branch from
  `_cost_bucket`; remove `saved_by_cache_usd` from every bucket call. Change the
  returned dict so the nine run fields live under a `run_info` key in the signed
  order, with only `costs` and `timings` beside it at the top level.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_summary.py -q` →
  exit 0 (assert `payload["run_info"]["run_name"]` etc.; assert
  `"saved_by_cache_usd" not in json.dumps(payload)`). Then full suite.
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥101 passed.
2. No separate lint/typecheck gate in this repo.
3. Fresh review: `git diff {baseline from PLAN.md}..HEAD` reviewed against this
   doc plus an over-engineering lens by a context that did not implement it
   (subagent given only the diff, this doc, and the lens; if unavailable, stop
   and ask the user). Fix findings, re-run 1.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥101 passed.
- A test builds a summary from results carrying populated `CallMeta` and asserts
  `run_info` nesting, a numeric `costs.total_usd`, and the absence of
  `saved_by_cache_usd`; another asserts an unknown meta forces bucket + run
  total to `unknown`.

## Rollback

To abandon this phase: `git reset --hard {baseline hash from PLAN.md's phase
table}`, then set this phase's Status to `blocked` in `PLAN.md` with a one-line
reason in your Phase-notes block.

## Failure modes

1. A `main.py` reader breaks (it shouldn't — it only writes) → if you find a
   real top-level field access, do NOT edit `main.py` from here; follow **If
   blocked** and flag it, because the plan mis-scoped the file list.
2. `equality_judges` sub-object structure changes → keep its `{license, url,
   copyright}` keys; only the numbers/`unknown_cost_calls` change.
3. Empty `results` (0 components) → `combine([])` must yield a known `$0`
   total (or guard `n==0`); mirror the existing `avg` guards.

## Anti-goals

Do not, even if it seems better:

- No compatibility layer / schema-version field / migration — DECISIONS says
  this is a direct schema change for new runs.
- No re-adding `saved_by_cache_usd` in any form.
- No touching the `timings` block or CSV writers.
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
   confirm the final `summary.json` shape (top-level keys `run_info`, `costs`,
   `timings`) so P6's docs describe the real output.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: real summary.json cost rollup + run_info grouping + drop saved_by_cache
HEAD: {git rev-parse --short HEAD} | Branch: {git branch --show-current}
Files changed: {git diff --name-only <baseline>..HEAD output}
Commands run: {the Verify/gate commands and their observed results}
Test status: {suite command + observed result}
Assumptions: {numbered, or "none"}
Open questions: {numbered, or "none"}
Next action: P5 per PLAN.md's table
```

## Outcome

Objective: real summary.json cost rollup + run_info grouping + drop saved_by_cache
HEAD: d12e134 | Branch: master
Files changed:

- docs/plans/cost-and-copyright-observability/PLAN.md
- src/summary.py
- tests/test_summary.py
Commands run:
- Entry: `pytest -q` → 113 passed; `git status --porcelain` → empty
- T1 Verify: `pytest tests/test_summary.py -q` → 7 passed
- T2 Verify: `pytest tests/test_summary.py -q` → 7 passed; full suite → 115 passed
- Validation gate: `pytest -q` → 115 passed; fresh review approve-with-notes (shrink avg ternaries) → fixed → 115 passed
Test status: `.\.venv\Scripts\python.exe -m pytest -q` → 115 passed
Assumptions: none
Open questions: none
Next action: P5 per PLAN.md's table
