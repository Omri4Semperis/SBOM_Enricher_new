<!-- TEMPLATE RULES: replace every {slot}; delete every comment like this
one; keep all other text verbatim in the instantiated doc. -->

# Plan: {plan name}

**Live document.** Unlike the old design, this file is written to during
execution. The executor of phase N may edit **only two files**: its own
`P{N}_{...}.md` doc and this `PLAN.md`. It updates its row in the phase
table, reflects concise notes into its own per-phase block, and leaves
**Incoming comments** in *another* phase's block here when it discovers
something that phase must know. It never edits another phase's `P*` doc.

**Execution:** one phase per fresh session via the `complex-plan-implement-phase`
skill. Fallback without that skill: pick the lowest-numbered phase whose
**Depends on** entries are all `done` in the table below and whose own Status
is `pending`; then follow that phase doc top to bottom — its Entry criteria,
Tasks, Validation gate, Exit criteria, and On completion sections are the
complete procedure. Read this whole `PLAN.md` first for cross-phase context
and any Incoming comments left in your phase's block.

## Goal

{2-6 sentences: what this plan achieves and for whom. No implementation
detail — that lives in phase docs.}

## Context

{Only what every phase needs: architecture sketch, key modules, constraints.
Phase-specific context belongs in that phase's Context capsule.}

## Phases

<!-- The single source of truth for phases, dependencies, and status. No
separate DAG diagram — this table is the dependency graph. Executors update
Status / Baseline / Updated for their own row only. Status is one of:
pending | in progress | done | blocked. Baseline is the short git hash
captured at phase start (blank until then). Updated is the date of the last
status change. -->

| Phase                                                | Purpose    | Depends on | Status  | Baseline | Updated |
| -                                                    | -          | -          | -       | -        | -       |
| [P1: {snake_case_title}](./P1_{snake_case_title}.md) | {one line} | -          | pending |          |         |
| [P2: {snake_case_title}](./P2_{snake_case_title}.md) | {one line} | P1         | pending |          |         |
| [P3: {snake_case_title}](./P3_{snake_case_title}.md) | {one line} | P1         | pending |          |         |

<!-- Filenames: P{N}_{snake_case_title}.md — lowercase, digits, underscores
only, so the links above never break. "Depends on" lists phase ids (P1, P2)
or "-". -->

## Test commands

<!-- The exact invocations, so no session ever guesses. Phase docs repeat
what they need — duplication is deliberate; this table is the master copy. -->

| Purpose    | Command     | Expected                  |
| -          | -           | -                         |
| full suite | `{command}` | {e.g. "exit 0, N passed"} |
| typecheck  | `{command}` | {expected}                |

## Phase notes

<!-- One block per phase. The planner seeds each with the general knowledge
OTHER phases need about this one (interfaces it exposes, decisions that
constrain neighbors, invariants). During execution the phase's own executor
reflects concise notes here (a generic version of the detail it wrote into
its P doc), and OTHER executors append Incoming comments — things they
discovered that this phase must act on. Keep entries dated and short; point
to the P doc for depth. A deliberately-failing test is recorded as a comment
here too (in the block of the phase that created it, then resolved in the
block of the phase that fixes it). -->

### P1: {title}

- **For other phases:** {what P1 exposes/decides that P2, P3… must rely on}
- **Notes:** {seeded empty or with planner caveats; executor appends dated lines}
- **Incoming comments:** {other phases append `- {date} [from P{X}] {note; see P{X} doc}`}

### P2: {title}

- **For other phases:** {…}
- **Notes:**
- **Incoming comments:**

### P3: {title}

- **For other phases:** {…}
- **Notes:**
- **Incoming comments:**

## On completion

Only after every phase shows `done` in the table above, in this order:

1. Graduate durable decisions out of the plan: anything in a Phase-notes
   block or a phase doc that a future maintainer must know goes to an ADR
   (invoke the `domain-modeling` skill; if unavailable, a dated note in the repo's docs).
2. Stamp the top of this file: `COMPLETED {YYYY-MM-DD} — historical record,
   not current truth`.
3. Move the whole plan directory to `docs/plans/archive/{plan-name}/`.

Stale plan docs poison future agents — archive, don't keep.
