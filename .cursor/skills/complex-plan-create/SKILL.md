---
name: complex-plan-create
metadata:
  version: 26-07-15-1
  provenance: Original to this library. No known upstream skill; uses generic multi-phase planning concepts only.
description: Create a multi-phase, multi-session plan as a docs/plans/ directory (a live PLAN.md plus one doc per phase, executed later via complex-plan-implement-phase). Use when the user asks to plan something complex or long-running, break work into phases, create a PLAN.md, make a multi-session or multi-week plan, or plan a large refactor/migration/feature spanning many sessions. Do NOT use for plans that fit in a single session, or to execute an existing plan (that's complex-plan-implement-phase).
---

You are the **planner**. A weaker model in a fresh session — the **executor**
— implements each phase later, reading that phase's doc plus `PLAN.md`. You
do all the thinking now; the executor barely thinks. Every decision left open
is a decision the executor will improvise, badly.

## Artifacts and ownership

One directory per plan, default `docs/plans/{plan-name}/` (follow repo
conventions if they differ):

| File                                                   | Written by                      | Executor may                                             |
| -                                                      | -                               | -                                                        |
| `PLAN.md` ([template](PLAN_template.md))               | planner seeds; executors update | update status, reflect comments, leave cross-phase notes |
| `P{N}_{snake_case}.md` ([template](PHASE_template.md)) | planner seeds; executors update | write detail freely — but only for its OWN phase         |

Status and discoveries live in these two docs, not side journals. The
templates carry the executor's write rules (each phase touches only its own
doc and `PLAN.md`); your job is just to seed the structure that makes those
rules followable — a per-phase block in `PLAN.md` that can receive
cross-phase notes.

## Workflow

1. **Gate:** for each candidate phase, try to write its one-line Demo and
   name the command that will verify it. If you can't, requirements are too
   fuzzy to plan — stop and propose a /grilling session instead.
2. **Decompose in chat first:** present phases and their dependencies for
   approval before writing any file.
3. **Write:** create the directory, `PLAN.md`, and every phase doc. Follow
   the template rules verbatim (replace `{slots}`, delete template comments,
   keep the rest). Seed each phase's PLAN.md block and Context capsule.
4. **Self-check** (run these, don't eyeball):
   - `wc -l PLAN.md P*_*.md` → PLAN.md and every phase doc under 200 lines
   - `grep -L "Demo:" P*_*.md` → empty (every phase has a Demo)
   - `grep -c "→" P*_*.md` per file → >0 (verify commands with expected output exist)
   - every `Depends on` id exists, no cycles (walk the table by hand — it's ≤10 rows)
   - every phase in the table has a matching `P{N}_{...}.md` file and a
     matching per-phase block in `PLAN.md`
   - test commands are real: run the full-suite command once and record its
     current output as the expected baseline
5. **Present:** point the user at the phase decomposition and the dependency
   table — not prose polish.

## Sizing — countable, not felt

- Phase: 2–5 tasks and ≤8 files touched. Over either limit → split.
  Under 2 tasks → merge into a neighbor.
- Plan: ≤10 phases. Needs more → split into sequential plans and say so.
- Never size by predicted context usage — you can't measure a future
  session. Count tasks and files.

## Vertical slices, never horizontal layers

Phases cut through every layer they touch and end in something observable —
the **Demo** line. Never "P1 schema, P2 API, P3 UI"; instead each phase is
one capability end to end. Greenfield plans start with a tracer bullet: the
thinnest end-to-end path proving the architecture. Mixed work orders as:
critical bug fixes > developer infrastructure > tracer bullet > quick wins >
refactors.

## Two docs, one job each

- `PLAN.md` is the **shared map**: the phase table with live status, the test
  commands, and one block per phase holding the general knowledge that *other*
  phases need plus the running comments (reflected detail, cross-phase
  incoming notes). An executor reads all of `PLAN.md` for context.
- `P{N}_{...}.md` is the **phase's own workspace**: the full implementation
  detail, the Context capsule, the tasks. Its executor reads it top to bottom
  and writes freely into it during implementation. It opens with a one-line
  **Plan:** orientation — the overall goal this phase serves — pointing at
  `PLAN.md` for depth rather than duplicating its Goal/Context.

Balance where facts go: implementation detail belongs in the phase doc; a
fact another phase needs belongs in that phase's `PLAN.md` block (reflected
concisely, pointing at the phase doc for depth). Duplicate a shared fact (like
the test command) into every phase doc that needs it — duplication is cheaper
than a confused executor.

## Context capsule

Each phase doc carries a 20–40 line **Context capsule** with everything about
the code that phase touches: paths, signatures, data shapes, invariants,
gotchas. The executor also has `PLAN.md`, so cross-phase facts can live there
instead — but anything specific to implementing *this* phase goes in the
capsule. If a capsule plus the phase's `PLAN.md` block still can't hold what a
phase needs, the phase is too big.

## Feedback loops

- Every task ends with a verify command and its expected output. Prefer
  red-green: the failing test is written into the task's steps.
- New behavior gets its tests in the same phase — never a trailing
  "testing phase".
- A test the plan deliberately leaves failing across phases is not tracked in
  a table; the executor that creates it leaves a comment in its phase's
  `PLAN.md` block, and the executor that fixes it leaves a resolving comment
  in its own. Executors in between acknowledge it without fixing it.

## Style

- Plain English; the reader is a weaker model with no context. Be brief by
  omitting detail that belongs elsewhere, never by compressing sentences
  into fragments — ambiguity costs more than tokens.
- Mermaid only where a diagram truly beats a paragraph. The phase table is
  the dependency source of truth; you rarely also need a graph.
- Choose the laziest approach that works (the /ponytail philosophy).
