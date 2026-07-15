# P6: docs_and_live_validation

**Plan:** cost-and-copyright-observability — make the enricher's spend real and
its copyright coverage complete. This phase is the terminal step; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** This doc is writable: record whatever detail you need here.
The other file you may edit is `PLAN.md` — your row in the phase table, a
concise reflection in your own Phase-notes block, and **Incoming comments** in
*another* phase's block when you discover something it must know. You never edit
another phase's `P*` doc. Status is tracked in `PLAN.md`'s table.

**Demo:** the two Full-Review Should-fixes are closed in the docs, BACKLOG #4/#6
are gone, and a recorded live run of one minimal Claude call and one minimal
GPT-4.1 call each shows a known (numeric) cost with zero unknown-cost calls.

**Goal:** finish the paper trail and prove the cost pipeline works against real
providers. Document the now-functional cost output + `unknown` semantics (SF1),
add the archive hash-chain note (SF2), remove the delivered BACKLOG levers, and
run the one-time live cost validation required by DECISIONS.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked**.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P5's Status is `done` in `PLAN.md`'s phase table
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥103 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

- **SF1** (`docs/archive/FULL-REVIEW_2026-07-15.md:33`, and `DECISIONS.md`
  "Documentation and backlog"): the first Should-fix "is resolved by documenting
  functional cost output and `unknown` semantics, not by adding an obsolete
  placeholder warning." Costs are now functional (P1–P4). Document, at the
  summary writer, that a cost cell/total is a real number when every contributing
  billable call is known and `unknown` (never `$0`) when any provider metadata is
  missing.
- **SF2** (`docs/archive/FULL-REVIEW_2026-07-15.md:41`, and `DECISIONS.md`): add a
  fact-checked note to the archived v2 plan explaining that its phase-table
  `Baseline` hashes and per-phase `Outcome` HEADs are NOT a contiguous hash chain
  (e.g. P2 Outcome HEAD `bd73882`, P3 baseline `234411c`) — baselines were
  captured per phase, not chained from the prior Outcome, so bisecting across
  phases will not follow a single line. Target file:
  `docs/plans/archive/v2-enricher/PLAN.md`.
- **BACKLOG** (`docs/BACKLOG.md`, `DECISIONS.md`): remove lever #4 (copyright
  fallbacks — delivered by P3) and #6 (LLM cost capture — delivered by P1–P4).
  "remaining rows keep their existing numbers" — do NOT renumber #1, #2, #3, #5.
- **Live validation** (`DECISIONS.md` "Validation"): after unit tests pass,
  validate cost integration once against a live minimal Claude call and a live
  minimal GPT-4.1 call. The check must demonstrate that ordinary valid provider
  responses produce known component costs and zero unknown-cost calls. This needs
  a working `claude` CLI and Azure credentials (`DefaultAzureCredential`); it is
  the one step that touches paid providers.
- Real signatures to call: `claude_client.infer_license(purl, lib_name, version,
  model) -> (dict, CallMeta)`; `gpt41_client.Gpt41Client().complete_json(system,
  user) -> (dict, CallMeta)` (or call `copyright.extract_copyright(text)`).
  Confirm exact shapes from the P1/P2 Outcomes. Use a cheap model
  (`claude-haiku-4-5`) and a tiny prompt.

## Files

**Touch (complete list):**

- `src/summary.py` — edit: **docstring only** — one note at the summary writer
  stating cost cells/totals are numeric when all billable calls are known, else
  `unknown` (never `$0`). No behavior change.
- `docs/plans/archive/v2-enricher/PLAN.md` — edit: append the SF2 hash-chain note.
- `docs/BACKLOG.md` — edit: remove levers #4 and #6; keep other numbers.
- `docs/archive/DECISIONS_2026-07-15_cost-and-copyright.md` — edit only if the
  Should-fix / live-validation stamps are still missing (already present as of
  archive); prefer recording live numbers in this doc's Outcome.

**Do not touch:** any other `src/` file (no behavior changes in this phase),
tests, and anything not listed. The live validation runs code but commits no
throwaway script — delete any scratch file before finishing.

## Tasks

### T1: close the documentation items

- Steps: (a) add the SF1 docstring note to `src/summary.py`. (b) append the SF2
  note to `docs/plans/archive/v2-enricher/PLAN.md`. (c) remove BACKLOG #4 and #6
  rows from `docs/BACKLOG.md`, leaving #1/#2/#3/#5 unrenumbered. (d) confirm
  both Should-fixes are stamped resolved in the archived decisions file (done
  before archive); skip if already present.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥103 passed
  (docstring/doc edits must not break the suite). And `git diff --stat` shows
  the intended files above (not the archived decisions file unless a stamp
  was still missing).
- Commit when green.

### T2: live minimal cost validation

- Steps: with real credentials available, run a minimal live check (a temporary
  `python -c` / scratch script, not committed): one `infer_license` call with
  `claude-haiku-4-5` on a tiny known package, and one GPT-4.1 call (via
  `extract_copyright` on a short real LICENSE snippet). Assert each returned
  `CallMeta` has `billable_calls >= 1`, `unknown_calls == 0`, and
  `total_usd()` is a number > 0. Record the exact commands and observed
  numbers in this doc's Outcome (the archived decisions validation note
  already holds the 2026-07-15 result). If credentials are unavailable in
  this environment, do NOT fake it — set the live check as pending, note it,
  and ask the user to run it (stop per **If blocked** guidance for this task
  only).
- Verify: the scratch check prints two numeric costs and `unknown_calls == 0`
  for both providers → paste the output into the Outcome. Delete the scratch
  file. `git status --porcelain` → only the intended doc changes.
- Commit when green (docs updated with the recorded result).

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
- `docs/BACKLOG.md` no longer contains levers #4 or #6; SF1 note present at the
  summary writer; SF2 note present in the archived v2 `PLAN.md`.
- The live-validation result (two numeric costs, zero unknown-cost calls) is
  recorded in this doc's Outcome (and already stamped in the archived
  decisions file) — or explicitly marked pending on the user if credentials
  were unavailable.

## Rollback

To abandon this phase: `git reset --hard {baseline hash from PLAN.md's phase
table}`, then set this phase's Status to `blocked` in `PLAN.md` with a one-line
reason in your Phase-notes block.

## Failure modes

1. No Azure/Claude credentials in this environment → do not fabricate results;
   mark the live check pending-on-user and record what command they should run.
2. Live call returns `unknown` cost (missing provider metadata) → that is a real
   regression in P1/P2 capture, not a doc issue; stop and file an Incoming
   comment on the owning phase's block, then report to the user.
3. Renumbering BACKLOG rows while deleting #4/#6 → forbidden; keep existing
   numbers, leave the gaps.

## Anti-goals

Do not, even if it seems better:

- No behavior changes in `src/` — only the `summary.py` docstring.
- No faking or hard-coding the live-validation numbers.
- No renumbering surviving BACKLOG rows.
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here"
  fixes. Spare capacity goes into verification, not scope.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list, do not edit another
phase's doc.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline + Updated.
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block,
   then follow `PLAN.md`'s **On completion** (graduate durable decisions to an
   ADR via `domain-modeling`, stamp `COMPLETED`, archive the plan directory).
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: close both Should-fixes, trim BACKLOG, live-validate cost capture
HEAD: 1ad57d6 | Branch: master
Files changed: docs/BACKLOG.md, docs/DECISIONS.md,
  docs/plans/archive/v2-enricher/PLAN.md, src/summary.py
  (configs/default.json also appears in this range — an unrelated commit,
  0e127ba, that landed from outside this session between this phase's two
  commits; not part of this phase's Touch list, not authored by this phase)
Commands run:
  - `.\.venv\Scripts\python.exe -m pytest -q` → 119 passed (run 3x: entry,
    after T1, after T2/gate)
  - `git diff --stat` after T1 → exactly the 4 Touch-list files
  - Live validation (scratch `_scratch_live_validation.py`, deleted after run):
    `infer_license("pkg:npm/left-pad@1.3.0", "left-pad", "1.3.0",
    "claude-haiku-4-5")` → billable_calls=1, unknown_calls=0,
    total_usd=0.4732403999999998
    `extract_copyright(<tiny MIT LICENSE snippet>)` (GPT-4.1) →
    billable_calls=1, unknown_calls=0, total_usd=0.000942
  - Fresh review subagent (generalPurpose, readonly) on `git diff
    f857bf2..HEAD` + this doc + ponytail-review tags: no doc-compliance
    violations, "Lean already. Ship." on over-engineering, confirmed the
    stray commit is out-of-band.
Test status: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, 119 passed
  (baseline requirement was ≥103)
Assumptions: none
Open questions: none
Next action: plan complete — follow PLAN.md On completion
```
