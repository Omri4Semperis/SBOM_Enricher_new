<!-- TEMPLATE RULES: replace every {slot}; delete every comment like this
one; keep all other text verbatim. Keep the instantiated doc under 200
lines. This doc plus its Context capsule plus PLAN.md is what the executor
reads — if a fact is needed to implement this phase, it lives here or in
PLAN.md. -->

# P{N}: {snake_case_title}

**Plan:** {plan name} — {one line: the overall goal this whole plan serves}.
This phase is one step toward it; read `PLAN.md`'s Goal and Context in full
before starting. That line orients you; `PLAN.md` is the source of truth, so
don't restate its detail here.

**Your workspace.** This doc is writable: during implementation, record
whatever detail you need here (decisions, dead ends, findings). The other
file you may edit is `PLAN.md` — your row in the phase table, a concise
reflection in your own Phase-notes block, and **Incoming comments** in
*another* phase's block when you discover something it must know. You never
edit another phase's `P*` doc. Status is tracked in `PLAN.md`'s table, not
here.

**Demo:** {one sentence: what a human can run or observe when this phase is done}

**Goal:** {2-4 sentences. What this phase adds, end to end.}

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] Each dependency's Status is `done` in `PLAN.md`'s phase table (skip if none)
- [ ] `{full test suite command}` → {expected, e.g. "exit 0, 42 passed"}
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

<!-- 20-40 lines, written by the planner. Everything the executor must know
about the code this phase touches: file roles, function signatures, data
shapes, invariants, gotchas. Cross-phase facts can live in PLAN.md instead;
this capsule holds what's specific to implementing THIS phase. If the capsule
plus this phase's PLAN.md block can't carry it, the phase is too big. -->

{capsule}

## Files

**Touch (complete list):**

- `{path}` — {create|edit|delete}: {why, one phrase}

**Do not touch:** {explicit paths that are nearby and tempting}, and
anything not listed under Touch. Needing an unlisted file means the plan is
wrong: record it as a note in this doc and a comment in your `PLAN.md` block;
if the phase can't proceed without it, follow **If blocked**.

## Tasks

<!-- 2-5 tasks, executed in order. Every step is an exact command or a
concrete edit ("add function X(sig) to path, called from Y"). Every task
ends with a verify command + expected output. No task leaves a decision
open — if a decision exists, the planner makes it here. -->

### T1: {name}

- Steps: {exact commands / concrete edits}
- Verify: `{command}` → {expected output}
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: {name}

- Steps: {…}
- Verify: `{command}` → {expected}
- Commit when green (write the message at commit time: a concise line describing what this task changed).

## Validation gate

All of these, in order, before Exit criteria:

1. `{full test suite command}` → {expected}
2. {lint/typecheck command if the repo has one} → {expected}
3. Fresh review: the diff `git diff {baseline placeholder — executor
   substitutes the hash recorded in PLAN.md at phase start}..HEAD` is
   reviewed against this doc plus an over-engineering lens by a context that
   did not implement it (subagent given only the diff, this doc, and the lens
   the executor skill supplies; if subagents are unavailable, stop and ask the
   user to review in a new session). Fix findings, re-run 1-2 — but a lens
   finding on something this doc explicitly ordered is NOT fixed; record it as
   a note here and, if it affects another phase, an Incoming comment in that
   phase's `PLAN.md` block.

## Exit criteria

Runnable proof the Demo is real:

- `{command}` → {expected output}
- `{command}` → {expected output}

## Rollback

To abandon this phase: `git reset --hard {baseline hash from PLAN.md's phase table}`, then set this phase's Status to `blocked` in `PLAN.md` with a one-line reason in your Phase-notes block.

## Failure modes

<!-- 2-3 most likely ways this phase goes wrong, each with a recovery. -->

1. {failure} → {recovery steps}
2. {failure} → {recovery steps}

## Anti-goals

Do not, even if it seems better:

- {anti-goal, e.g. "no refactor of X — P4 owns it"}
- Nothing beyond this doc's Tasks: no extra abstractions, options, or
  "while I'm here" fixes. Spare capacity goes into verification, not scope.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list, do not edit another
phase's doc.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (the start
   hash) and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block
   — what other phases now need to know, and any Incoming comments for other
   phases. Keep it short; write the full detail below and point to it.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: {phase goal, one line}
HEAD: {git rev-parse --short HEAD} | Branch: {git branch --show-current}
Files changed: {git diff --name-only <baseline>..HEAD output}
Commands run: {the Verify/gate commands and their observed results}
Test status: {suite command + observed result}
Assumptions: {numbered, or "none"}
Open questions: {numbered, or "none"}
Next action: {the next eligible phase per PLAN.md's table, or "plan complete"}
```
