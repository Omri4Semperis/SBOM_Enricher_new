# P1: claude_cost_capture

**Plan:** cost-and-copyright-observability — make the enricher's spend real and
its copyright coverage complete. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** This doc is writable: record whatever detail you need here
(decisions, dead ends, findings). The other file you may edit is `PLAN.md` —
your row in the phase table, a concise reflection in your own Phase-notes
block, and **Incoming comments** in *another* phase's block when you discover
something it must know. You never edit another phase's `P*` doc. Status is
tracked in `PLAN.md`'s table, not here.

**Demo:** after a run, `results_*_extended.csv` shows a real `inferencer_cost_usd`
from Claude's CLI `total_cost_usd` and a populated `inferencer_raw_response` —
instead of `unknown` / empty.

**Goal:** introduce the shared `CallMeta` cost accumulator in `src/pricing.py`,
make `claude_client.infer_license` capture cost / raw / tokens for every
billable attempt (including parse-rejected ones), store it on
`ComponentResult.license_meta`, and surface the license cost + raw into the
extended CSV. This is the metadata backbone every later phase reuses.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, 95 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

- `src/pricing.py` today: `UNKNOWN_COST = "unknown"`, `MODEL_PRICING`,
  `compute_cost(...)-> float | None`, `format_cost(float|None) -> str`. Add
  `CallMeta` here.
- `src/claude_client.py`: `infer_license(purl, lib_name, version, model) -> dict`
  (keys `license_name, license_code_url, reasoning, attempts`). Internals:
  `_claude_once` runs the CLI then `_parse_cli_stdout`; retries via
  `with_retries(once, classify=...)`; `attempts` counted in a closure `{"n":0}`.
- **CLI JSON wrapper** (see `knowledge/old_code/src/client.py:54-67`):
  `json.loads(stdout)` → dict with `total_cost_usd` (on the wrapper, readable
  even when the inner payload is malformed) and optional `usage`. Payload is
  under `structured_output`/`result`.
- **Decision** (`DECISIONS.md` "Cost and call metadata"): capture cost for every
  billable attempt, incl. parse/contract-rejected ones. Claude cost = the CLI's
  authoritative `total_cost_usd` (do NOT recompute from tokens). Missing metadata
  → `unknown`, never `$0`.
- `src/pipeline.py`: `ComponentResult` dataclass; `process_component` calls
  `infer_license` (~line 77); cache-hit path returns early (~66-74, no LLM call,
  `from_cache=True`).
- `src/results_csv.py`: `ExtendedWriter.write_row` (~166-168) currently sets
  `inferencer_raw_response=""` and `inferencer_cost_usd=UNKNOWN_COST`
  (empty when `from_cache`). Both columns already in `EXTENDED_EXTRA_COLUMNS`.
- `tests/test_summary.py::_fake_infer` returns a dict with no cost — keep it
  working (missing `total_cost_usd` → unknown, not a crash).

## Files

**Touch (complete list):**

- `src/pricing.py` — edit: add `CallMeta` dataclass + `combine`/`total_usd`.
- `src/claude_client.py` — edit: capture `total_cost_usd`/raw per attempt,
  return meta alongside the result dict (or via an out-param accumulator).
- `src/pipeline.py` — edit: add `license_meta: CallMeta` to `ComponentResult`;
  store the meta returned by `infer_license`; cache hit → empty `CallMeta`.
- `src/results_csv.py` — edit: fill `inferencer_cost_usd` / `inferencer_raw_response`
  from `result.license_meta`.
- `tests/test_pricing.py` — edit: `CallMeta` accumulation + `total_usd` unit tests.
- `tests/test_claude_client.py` — edit: cost captured on success and on parse-reject.
- `tests/test_results_csv.py` — edit: extended row shows numeric license cost.

**Do not touch:** `src/summary.py` (P4 owns the run-level rollup — license
bucket stays `unknown` there until P4; leave it), `src/gpt41_client.py`,
`src/copyright.py`, `src/equality.py`, and anything not listed above.

## Tasks

### T1: add the CallMeta accumulator to pricing

- Steps: in `src/pricing.py` add a dataclass `CallMeta` with
  `known_usd: float = 0.0`, `billable_calls: int = 0`, `unknown_calls: int = 0`,
  `raws: list[str] = field(default_factory=list)`. Add `total_usd(self) ->
  float | None` returning `None` if `unknown_calls > 0` else `known_usd`. Add a
  helper to record one attempt: `add_call(self, *, cost_usd: float | None, raw:
  str)` that increments `billable_calls`, appends `raw`, and either adds
  `cost_usd` to `known_usd` or increments `unknown_calls` when `cost_usd is
  None`. Add `cost_cell(self) -> str` returning `format_cost(self.total_usd())`.
  Add a module-level `combine(metas: Iterable[CallMeta]) -> CallMeta` that sums
  all four fields (used by P4's run-level rollup).
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_pricing.py -q` →
  exit 0, all passed (new tests: one known call → numeric total; one unknown
  call mixed with a known call → `total_usd()` is `None` / cell `unknown`;
  `combine` sums `known_usd`, `billable_calls`, `unknown_calls`).
- Commit when green.

### T2: capture Claude cost/raw per attempt

- Steps: in `src/claude_client.py`, thread a `CallMeta` accumulator through the
  retry loop. In `_claude_once` (or a wrapper), after the CLI returns exit 0,
  `json.loads` the wrapper, call `meta.add_call(cost_usd=data.get(
  "total_cost_usd"), raw=stdout.decode(errors="replace"))` **before** calling
  `_parse_cli_stdout` / validating the payload — so a `ParseFailure` still
  leaves the cost recorded. Non-zero exit (transient/hard) records nothing (no
  billable response). Change `infer_license` to also return the accumulated
  `CallMeta` (e.g. return `(dict, CallMeta)`, or attach it under a private key
  the pipeline reads then strips). Keep the existing `attempts` counter and the
  `_unknown(...)` fallbacks intact.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_claude_client.py -q`
  → exit 0 (new tests: mocked CLI stdout with `total_cost_usd` → meta has one
  billable call, numeric total; a first attempt with valid wrapper but broken
  inner payload then a good retry → 2 billable calls, cost summed).
- Commit when green.

### T3: store meta on the result and write it to the extended CSV

- Steps: in `src/pipeline.py` add `license_meta: CallMeta = field(
  default_factory=CallMeta)` to `ComponentResult`; set it from what
  `infer_license` now returns; on the cache-hit early return leave the default
  empty `CallMeta`. In `src/results_csv.py`, replace the placeholder
  `inferencer_cost_usd` / `inferencer_raw_response` writes with
  `result.license_meta.cost_cell()` (empty string when `from_cache`) and
  `"\n---\n".join(result.license_meta.raws)`.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_results_csv.py
  tests/test_pipeline.py -q` → exit 0. Then full suite (Validation gate).
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥96 passed.
2. No separate lint/typecheck gate in this repo.
3. Fresh review: `git diff {baseline from PLAN.md}..HEAD` reviewed against this
   doc plus an over-engineering lens by a context that did not implement it
   (subagent given only the diff, this doc, and the lens; if unavailable, stop
   and ask the user). Fix findings, re-run 1. A lens finding on capturing raw of
   rejected attempts is NOT fixed (this doc ordered it); record it as a note.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥96 passed.
- A test asserts that after a mocked Claude call carrying `total_cost_usd`, the
  extended CSV `inferencer_cost_usd` cell is numeric (not `unknown`) and
  `inferencer_raw_response` is non-empty.

## Rollback

To abandon this phase: `git reset --hard {baseline hash from PLAN.md's phase
table}`, then set this phase's Status to `blocked` in `PLAN.md` with a one-line
reason in your Phase-notes block.

## Failure modes

1. No `total_cost_usd` on the wrapper → `add_call(cost_usd=None)` → `unknown`
   cell (correct, not a bug).
2. Fakes in `tests/test_summary.py` / `tests/test_pipeline.py` return the old
   shape → update those fakes to the new return, or have the pipeline tolerate a
   plain-dict return (default empty `CallMeta`); do not widen scope further.

## Anti-goals

Do not, even if it seems better:

- No recomputing Claude cost from tokens — Claude uses CLI `total_cost_usd`.
- No touching `src/summary.py` (P4) and no new per-call JSON artifact — raws
  live in the CSV column (joined).
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here"
  fixes. Spare capacity goes into verification, not scope.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list, do not edit another
phase's doc.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (the start
   hash) and Updated (today).
3. In `PLAN.md`, reflect a concise outcome — confirm the final `CallMeta` field
   names and `infer_license` return shape so P2–P5 rely on the real signature.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: capture Claude cost/raw on results + extended CSV
HEAD: {git rev-parse --short HEAD} | Branch: {git branch --show-current}
Files changed: {git diff --name-only <baseline>..HEAD output}
Commands run: {the Verify/gate commands and their observed results}
Test status: {suite command + observed result}
Assumptions: {numbered, or "none"}
Open questions: {numbered, or "none"}
Next action: P2 per PLAN.md's table
```
