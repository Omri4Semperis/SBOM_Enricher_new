# DEFERRED — grilling of `docs/SUGGESTIONS.md`

> Items pushed out of the committed "fact-grade-first" tranche during the
> grilling of `docs/SUGGESTIONS.md`. Each has an owner and a trigger to revisit.
> Committed decisions live in `docs/DECISIONS.md`.

## Deferred

### Third equality verdict — `FALSE-GT-suspect` (branch D)

**What:** A third judge verdict beyond TRUE/FALSE, meaning "our answer and the GT
differ, and the evidence backs *our* side" — turning a pile of "misses" into a
reviewable GT-suspect pile.

**Why deferred:**
1. Breaks the `CONTEXT.md` **Equality** contract (verdict is strictly TRUE/FALSE).
2. Requires a human-review workflow for the GT-suspect pile that does not exist.
3. Asks the same system being measured to certify its own answers as
   "independently grounded" — the branch-A incentive trap ("truthful, not the
   number"). An LLM grading its own homework as GT-suspect hollows out the score.

**Preferred future form (grill on its own before building):** a *deterministic,
evidence-based* GT-suspect flag — e.g. copyright holder lexically matches the
repo/package owner; agent's license file is real and on-topic — NOT a subjective
LLM verdict.

**Trigger to revisit:** after the committed fact-grade tranche lands and a re-run
shows the residual Mismatch pile is dominated by genuine agent-vs-GT
disagreements worth human triage.

**Owner:** Omri.

### Positive copyright extraction from NOTICE / source headers (branch F)

For Apache-2.0-style LICENSEs with no holder line, extract the *correct* holder
(e.g. "The OpenTelemetry Authors") from NOTICE files or source-file headers,
rather than only rejecting the wrong one. Deferred: adds a new source to the
ADR-0004 chain (more code + LLM cost) for ~13 rows; the reject-only guard already
makes those rows honest (UNKNOWN). Trigger: copyright recall becomes the binding
constraint on a score-bearing run. Owner: Omri.

### Unscoreable → Hit upgrade via canonical SPDX text (branch C)

Upgrade an `Unscoreable` URL row to `Hit` only when the agent's downloaded file
matches a canonical SPDX license text for the declared license id. Deferred:
needs an SPDX text corpus. Trigger: if the `Unscoreable` bucket grows large
enough that "not scored" is itself misleading. Owner: Omri.

## Out of scope for this line of work

- Root-cause #7 — SPDX-expression set comparator for compound licenses (~7 rows).
  Genuine method gap but low volume; not fact-grade-cheap.
