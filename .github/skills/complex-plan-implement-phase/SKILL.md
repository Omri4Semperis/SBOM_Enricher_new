---
name: complex-plan-implement-phase
metadata:
  version: 26-07-14-1
  provenance: Original to this library, paired with complex-plan-create. Distinct from mattpocock/skills' PRD-based `implement`.
description: Execute one phase of a multi-phase plan created with the complex-plan-create skill (a docs/plans/{plan-name}/ directory with a live PLAN.md and PN_{title}.md phase docs). Use when the user asks to implement, execute, run, continue, or kick off a phase of an existing plan, says "next phase" or "continue the plan", or points at a plan directory or phase doc asking for it to be executed. Do NOT use for creating or editing plan structure — that's complex-plan-create.
---

You are the **executor** of one phase. The planner already made every
decision; your job is to follow the phase doc exactly, verify constantly, and
record — never to think up scope. You may edit **exactly two files**: this
phase's own `P{N}_{...}.md` doc (your workspace, write freely) and `PLAN.md`
(status, a concise reflection in your Phase-notes block, and Incoming comments
you leave in *other* phases' blocks). You never edit another phase's doc.

## Pick the phase

1. Locate the plan directory (default `docs/plans/{plan-name}/`; ask if
   several are active and the user didn't say).
2. If the user named a phase, that's the phase. Otherwise read `PLAN.md`'s
   phase table and pick the lowest-numbered phase whose every dependency
   shows Status `done` and whose own Status is `pending`.
3. A phase with Status `in progress` was interrupted. Ask the user before
   resuming. Resume procedure: re-run all Entry criteria except the
   clean-tree check, read `git log --oneline` since the Baseline hash in the
   table to see what landed, re-run the Verify command of the last committed
   task, and continue from the first task whose Verify fails.
4. Nothing eligible → report which phases block on what, and stop.

## Read

Read the phase doc fully — it is your primary implementation context — and
read all of `PLAN.md` for cross-phase context: the Phase-notes block for this
phase (especially any **Incoming comments**, which amend your doc), what
neighboring phases expose, and the test commands. Do not read other phases'
`P*` docs and do not explore the repo beyond the files this phase's **Files →
Touch** list names. If the doc leaves a real decision open, has vague
criteria, or its capsule plus its PLAN.md block don't cover something you
need — that is a planning bug, not your cue to improvise: follow the doc's
**If blocked** section.

## Execute

1. **Entry criteria:** run every command. A red test that some phase's
   `PLAN.md` notes flag as a deliberate future-fix is an expected failure, not
   a regression (see **Expected-failing tests**); any other failure →
   **If blocked**. Re-read the Incoming comments in this phase's `PLAN.md`
   block — they amend your doc.
2. **Record the baseline:** `git rev-parse --short HEAD`. This hash is the
   review-diff base and the rollback target. In `PLAN.md`'s phase table, set
   this phase's Status to `in progress`, write the hash into Baseline, and set
   Updated to today.
3. **Drift check.** The plan docs can be stale — SDLC is messy, and the repo
   may have moved since the plan was written or the last phase ran. Scan
   `git log --oneline` and `git diff` since the most recent `done` phase's
   Baseline (the plan's starting point if there is none). This is not a review
   of that work: look only for changes that collide with *this* phase — a
   **Files → Touch** file already modified, a path the doc assumes that was
   renamed or deleted, a signature or API the doc's Steps call that changed.
   Found something with real consequences → tell the user the specific
   collision and a suggested adjustment before touching code; if the doc no
   longer works as written, **If blocked**. Nothing relevant → proceed.
4. **Tasks, in order.** Each: follow Steps exactly, run Verify, compare to
   the expected output, then commit — writing a concise message that describes
   what the task changed (the planner does not prescribe it). A Verify
   mismatch you can fix inside the task's file list, fix; anything else →
   **If blocked**.
5. **Deviations:** the moment reality disagrees with the doc (wrong path,
   extra file needed, different command), record it — write the detail in this
   phase's own doc and a concise note in your `PLAN.md` Phase-notes block. If
   it affects another phase, add an Incoming comment to that phase's `PLAN.md`
   block pointing back to your doc. Then continue only if the doc's
   instructions still work as written; otherwise **If blocked**. Never
   silently adapt.
6. **Validation gate**, in the doc's order — the same expected-failing rule
   applies to the suite run here (see **Expected-failing tests**). The fresh
   review means a context that did not implement: launch a Cursor Task
   subagent (`generalPurpose`, `readonly: true`) given only the diff
   (`git diff {baseline}..HEAD`), the phase doc, and — as the
   over-engineering lens — the tag definitions (delete/stdlib/native/yagni/shrink)
   read from this skill's sibling `../ponytail-review/SKILL.md` (absent → ask for
   over-engineering in general, don't re-derive the tags). Ask for findings
   against the doc's criteria plus that lens. The lens never overrides the doc:
   something the doc explicitly ordered stays built — record the lens's objection
   as a note in the phase doc (and, if it touches another phase, an Incoming
   comment in `PLAN.md`) for the planner, instead of fixing it. No Task/subagents
   available → stop and tell the user: "open a fresh session and review
   `git diff {baseline}..HEAD` against {phase doc path}, plus apply the
   `ponytail-review` skill on that diff" — do not self-review.
7. **Exit criteria**, then **On completion** exactly as written in the doc
   (set Status `done` in `PLAN.md`, reflect a concise outcome into your
   Phase-notes block, write the full **Outcome** section into the phase doc).

## Expected-failing tests

A phase may deliberately leave a test red until a later phase supplies the
missing piece. These live as comments in `PLAN.md` Phase-notes blocks, never a
table. Handle them by your role:

- **You create one** — a test you write now is meant to stay red until a later
  phase: record it in your Phase-notes block naming the exact test, why it
  fails, and the phase that will make it pass ("`test_dlq_retry` fails on
  purpose until P6 wires the queue"). Note the exception in your Exit criteria
  so it does not read as a failure.
- **You pass through one** — a prior phase's note names a test still red and
  you are not its fixer: confirm the still-red test matches that note, add one
  line to your Phase-notes block acknowledging it ("`test_dlq_retry` still red
  as expected, left for P6 — not fixing"), and treat it as expected in Entry
  criteria and the Validation gate. Any red test NOT covered by such a note is
  a regression → **If blocked**.
- **You fix one** — you are the phase named as the fixer: the test goes green
  as part of your work, and you record the closure in your Phase-notes block
  ("`test_dlq_retry` now green — closed out from P4").

## After the phase

- Before reporting, confirm any test you left deliberately red for a later
  phase — or closed out — is recorded per **Expected-failing tests**.
- Report in chat: phase done, Demo instructions, next eligible phase per the
  table. There is no handoff file — the record lives in the phase doc's
  Outcome section and your `PLAN.md` Phase-notes block.
- If this was the last phase the user wants and every phase shows `done`,
  follow `PLAN.md` → **On completion** (graduate decisions, stamp, archive) —
  the stamp is the one sanctioned structural edit, and it happens only here.
