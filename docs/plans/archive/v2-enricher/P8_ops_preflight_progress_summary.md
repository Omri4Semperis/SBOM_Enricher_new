# P8: ops_preflight_progress_summary

**Your workspace.** This doc is writable. The other file you may edit is
`PLAN.md` — your table row, a concise Phase-notes reflection, and **Incoming
comments** in another phase's block. Never edit another phase's `P*` doc.

**Demo:** a run prints a live progress bar with ETA, writes
`results_{model_short}_{n}_extended.csv` and a `summary.json` with per-phase
cost/time buckets; with a provider mocked unreachable, the run fails fast before
any worker starts.

**Goal:** Add the operational shell around the working pipeline: a startup
dual-provider preflight (fail-fast), a live progress bar + ETA, the exhaustive
`results_*_extended.csv`, and `summary.json` run aggregates. This is the last
phase — it makes a real run observable and re-createable.

## Entry criteria

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P6 and P7 Status are both `done`
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed
- [ ] `git status --porcelain` → empty

## Context capsule

- All enrichment + audit + cache stages exist. This phase only observes and
  gates; it does not change enrichment logic. Confirm result-object fields,
  per-attempt logs (P3/P4), `from_cache` flag (P6), grades/reasons (P7) in prior
  Phase-notes — they feed the extended CSV and summary.
- Locked preflight (DECISIONS "Startup connectivity preflight"): before spawning
  workers, probe BOTH providers — a trivial `claude` invocation and an Azure
  token acquisition (`DefaultAzureCredential.get_token(AZURE_TOKEN_SCOPE)` and/
  or a minimal GPT-4.1 call). Unreachable/unauthenticated after retries ⇒
  fail-fast with a clear message. Preflight is itself retried: **≥3 attempts per
  provider with increasing DETERMINISTIC backoffs, no jitter** (e.g. 2s, 4s,
  6s) — distinct from the mid-run policy. Mid-run auth death still falls under
  "no circuit-breaker, all-`UNKNOWN`, user Ctrl-C". Old `_ensure_azure_auth_ready`
  is a reference for the Azure half.
- Locked progress (DECISIONS "Progress display"): live block-glyph bar +
  `done/total`, extended with ETA from elapsed + completed rate. Reference:

```py
def progress_bar(done: int, total: int, width: int = 35) -> str:
    filled = int(width * done / total) if total else 0
    return f"[{'█' * filled}{'░' * (width - filled)}] {done}/{total}"
```

- Locked extended CSV (DECISIONS "Run output layout", column-order decision):
  `results_{model_short}_{n}_extended.csv` = everything — raw responses per LLM,
  normalized + un-normalized values, approximate costs, cache hit/miss, per
  phase, plus per-component grades/reasons (from P7). Same writer conventions as
  P2 (`utf-8-sig`, `csv.DictWriter`, streamed).
- Locked `summary.json` (DECISIONS "Run output layout" + "summary.json costs &
  timings"): paths, run id, run name (if config supplies one), model, workers,
  components count, UTC start/end, plus:
  - **Cost buckets per phase:** license inference · copyright extraction ·
    equality judges (license/url/copyright) — each `total_usd`,
    `avg_per_row_usd`, `unknown_cost_calls`, and `saved_by_cache_usd` where
    cache applies. No consistency-judge bucket.
  - Claude cost: prefer CLI `total_cost_usd` when present. GPT-4.1: tokens ×
    ported `MODEL_PRICING` + `compute_cost`; missing price ⇒ record cost
    **unknown**, not `$0`.
  - **Time:** wall-clock total + `avg_seconds_per_row`; per-phase averages
    (infer / download / copyright / equality) from Story timings. Download is
    time-only.
  - Aggregates: `costs.total_usd`, `costs.avg_per_row_usd`, bottom-line time
    block.
  - **Pricing table is a source constant, NOT `default.json`** (like retry
    constants). Old `config.py` `ModelPricing`/`MODEL_PRICING`/`compute_cost`
    and `cost_tracking.py` are references.
- To capture costs/timings, the earlier phases already store per-attempt data on
  the result object / Story. If a needed field is missing, DO NOT edit another
  phase's code silently — record it here and leave an Incoming comment in that
  phase's `PLAN.md` block; add the minimal capture in a P8-owned file if it can
  live there, else follow **If blocked**.

## Files

**Touch (complete list):**

- `src/preflight.py` — create: `preflight(config)` probing both providers with
  deterministic backoff; raises `SystemExit` on failure.
- `src/progress.py` — create: `progress_bar` + ETA formatting; a thread/async-
  safe counter the pool updates.
- `src/pricing.py` — create: `MODEL_PRICING` constant + `compute_cost(...)`
  (GPT-4.1 tokens→usd; unknown price → unknown, not 0).
- `src/summary.py` — create: aggregate result objects → `summary.json`.
- `src/results_csv.py` — edit: add the extended-CSV writer (or a sibling
  `extended_csv.py` if cleaner — keep to these files).
- `src/main.py` — edit: call `preflight` before the pool; drive progress during
  the run; write extended CSV + `summary.json` at the end.
- `tests/test_preflight.py`, `tests/test_progress.py`, `tests/test_pricing.py`,
  `tests/test_summary.py` — create.

**Do not touch:** enrichment/audit/cache logic (reuse/observe only),
`knowledge/`.

## Tasks

### T1: preflight

- Steps: `src/preflight.py` — probe Claude (trivial CLI call) + Azure (token /
  minimal call), ≥3 deterministic attempts each (2s,4s,6s), fail-fast
  `SystemExit` with a clear message.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_preflight.py` →
  exit 0 (mock both probes: success → returns; persistent failure → `SystemExit`
  after the attempts; patch sleep).
- Commit when green.

### T2: pricing + progress

- Steps: `src/pricing.py` `MODEL_PRICING` + `compute_cost` (unknown price →
  unknown); `src/progress.py` bar + ETA + safe counter.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_pricing.py
  tests/test_progress.py` → exit 0 (known price → usd; missing price → unknown
  marker, not 0; bar/ETA formatting at 0/total, mid, done).
- Commit when green.

### T3: extended CSV + summary + wire

- Steps: extended-CSV writer (all raw/normalized/cost/cache/per-phase +
  grades); `src/summary.py` building the locked `summary.json` shape;
  `src/main.py` wires preflight → progress → extended CSV + summary.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_summary.py
  tests/test_pipeline.py` → exit 0 (fixture run → extended CSV has the raw/cost/
  cache columns; `summary.json` has per-phase buckets + aggregates + UTC times).
- Commit when green.

## Validation gate

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. Fresh review of `git diff {baseline}..HEAD` by a `generalPurpose` readonly
   subagent (diff + this doc + over-engineering lens). Fix findings, re-run 1;
   ordered-behavior findings recorded not fixed.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- Test proving preflight fail-fast (mocked unreachable provider → `SystemExit`
  before workers) and a fixture run producing extended CSV + valid
  `summary.json` both pass.

## Rollback

`git reset --hard {baseline hash from PLAN.md}`, Status `blocked` + one-line
reason in Phase-notes.

## Failure modes

1. Live provider calls in preflight tests → mock both probes; no network in the
   suite.
2. Recording `$0` for an unknown price → must be an explicit "unknown cost"
   marker (locked), never `0`.
3. Needing data an earlier phase didn't capture → leave an Incoming comment in
   that phase's `PLAN.md` block; add minimal capture in a P8-owned file or
   follow **If blocked** — do not silently edit another phase's code.

## Anti-goals

- No budget / wall-clock cap / mid-run circuit-breaker — accepted residual
  risks (BACKLOG), not this phase.
- No consistency-judge cost bucket (dropped in v2).
- No pricing knobs in `default.json` — source constant only.
- Nothing beyond this doc's Tasks.

## If blocked

Set Status `blocked` in `PLAN.md` (Baseline + Updated), one-line reason in
Phase-notes, report and stop.

## On completion

1. Re-check Entry/Validation/Exit.
2. `PLAN.md`: Status `done`, Baseline + Updated.
3. Reflect into Phase-notes: final `summary.json` shape + extended-CSV columns.
4. Record full **Outcome** here (same shape as P1's). Since this is the last
   phase, Next action = "plan complete" and trigger PLAN.md's On completion
   (graduate decisions → ADR, stamp, archive).

## Outcome

Objective: preflight + progress + extended CSV + summary.json
HEAD: b5d63f8 | Branch: master
Files changed:
- docs/BACKLOG.md
- docs/plans/archive/v2-enricher/PLAN.md
- docs/plans/archive/v2-enricher/P8_ops_preflight_progress_summary.md
- src/main.py
- src/preflight.py
- src/pricing.py
- src/progress.py
- src/results_csv.py
- src/summary.py
- tests/conftest.py
- tests/test_preflight.py
- tests/test_pricing.py
- tests/test_progress.py
- tests/test_summary.py
Commands run:
- Entry: `pytest -q` → 78 passed; porcelain empty; baseline `2d0e27a`
- T1: `pytest -q tests/test_preflight.py` → 4 passed
- T2: `pytest -q tests/test_pricing.py tests/test_progress.py` → 7 passed
- T3: `pytest -q tests/test_summary.py tests/test_pipeline.py` → 12 passed
- Gate: `pytest -q` → 92 then 94 passed after review fixes; review FAIL→fixed
- On completion: archive to `docs/plans/archive/v2-enricher/`; stamp COMPLETED 2026-07-15
Test status: `.\.venv\Scripts\python.exe -m pytest -q` → 94 passed
Assumptions:
1. Four preflight attempts (initial + sleeps 2/4/6) satisfy "≥3 attempts (e.g. 2s,4s,6s)".
2. Costs stay `unknown` until BACKLOG #6; Story parse covers timings/reasons only.
3. `tests/conftest.py` autouse noop-preflight is an allowed deviation (suite must not hit live providers).
Open questions: none
Next action: plan complete
Deviations:
- Touch list omitted `tests/conftest.py`; edited for autouse preflight noop.
- `.gitignore` `runs/` already present (P2 Incoming resolved, no edit).
- Extended CSV raw/cost fields empty/`unknown` with Incoming on P3/P5/P6/P7 + BACKLOG #6.
- No new ADR: ops already LOCKED in DECISIONS.md; cost capture parked as BACKLOG #6.
