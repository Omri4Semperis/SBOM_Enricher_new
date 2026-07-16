---
name: grilling
license: MIT
metadata:
  version: 26-07-07-1
  upstream: https://github.com/mattpocock/skills
  provenance: Adapted from mattpocock/skills (productivity/grilling, MIT (c) 2026 Matt Pocock). Merged grill-me/grill-with-docs behavior; branch checklist and sign-off added locally.
description: Grill the user relentlessly about a plan or design — a one-question-at-a-time interview that stress-tests every decision until shared understanding is reached and signed off. Use when the user says "grill me", "grill this plan", "stress-test this plan/design", "poke holes in this", "interrogate me about this design", "play devil's advocate", or wants a plan challenged before building. Do NOT use for focused terminology work (that's domain-term-alignment) or for anything about cooking.
---

Interview the user relentlessly about a plan until shared understanding is
reached. One question at a time — multiple questions at once are
bewildering. Every question comes with your recommended answer.

## 0. Subject

Name the thing being grilled: the plan, doc, or design under discussion. If
nothing is in context, ask the user to point at it (file or description).
Restate it in one line and get a nod before the first question.

## 1. Branch list — the session's backbone

Before the first question, enumerate the design's branches as a visible
checklist (adapt to the subject): goals and non-goals, scope boundaries,
data and state, interfaces/contracts, failure handling, security and
permissions, operations, open risks.

- Show the checklist with each branch marked open `[ ]` or resolved `[x]`.
- Work one branch at a time, resolving dependencies between decisions in
  order.
- After resolving a branch (or adding a discovered one), re-show the
  updated checklist. This list is your position — never rely on memory of
  where the interview was.

## Term gate

Pause the interview and invoke the `domain-term-alignment` skill
(read and follow `../domain-term-alignment/SKILL.md`) when **both** hold:

1. A mismatch signal: the user uses two words for one concept, one word for
   two concepts, a term differently from you, or you introduced a term the
   user hasn't confirmed.
2. The term affects requirements, architecture, contracts, data shape,
   tests, permissions, or user expectations.

A merely important term with no mismatch signal needs no pause. Before
pausing, mark the current branch and pending question in the checklist;
resume exactly there. Grilling never writes `CONTEXT.md` — all recording
happens inside `domain-term-alignment`, which routes writes through
`domain-modeling`.

## Codebase checks

A question the codebase can answer, check briefly (a few greps, not a
survey) instead of asking. Inconclusive → ask the user and say what was
checked. Code contradicting the user's language → surface it and apply the
term gate.

## Closing

When every branch is resolved or explicitly deferred:

1. Write a recap: one line per decision, plus a list of deferred items with
   who owns each.
2. Ask the user to confirm the recap. The session ends only on explicit
   sign-off — "looks good" on the recap counts; silence does not.
3. Offer ADRs for durable decisions via the `domain-modeling` skill (its
   criteria decide; don't push).

Do not start building the plan. Grilling ends at shared understanding.
