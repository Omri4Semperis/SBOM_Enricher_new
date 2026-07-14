---
name: domain-modeling
license: MIT
metadata:
  version: 26-07-07-1
  upstream: https://github.com/mattpocock/skills
  provenance: Adapted from mattpocock/skills (engineering/domain-modeling, MIT (c) 2026 Matt Pocock). Sole-writer declaration and per-directory ADR numbering added locally.
description: Own and maintain the project's domain-model documents — the CONTEXT.md glossary and ADRs (architecture decision records). Use when the user wants to record an architectural decision, write an ADR, update or create CONTEXT.md or a glossary/ubiquitous language, or when another skill (term-alignment, grilling) hands over a resolved term or decision to record. For resolving a live vocabulary mismatch use term-alignment; do NOT use for editing model/entity classes in code — this skill produces documentation, not code changes.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design — challenge terms, invent edge-case scenarios, and write the glossary and decisions down the moment they crystallise.

**This skill is the only writer of `CONTEXT.md` and ADR files.** Other
skills (domain-term-alignment, grilling) hand terms and decisions here; they never
edit the files themselves.

## Kickoff — always first

Before any challenge, update, or create: use the Glob tool for
`**/CONTEXT-MAP.md`, then `**/CONTEXT.md`. A map → read it, pick the context the topic belongs to
(unclear → ask); only a `docs/CONTEXT.md` → single context; neither → no
glossary exists yet — create one lazily at the first recorded term, in
`docs/` unless a map is being introduced. Never create a `docs/CONTEXT.md`

## When invoked by another skill

Mid-flow (e.g. from grilling or domain-term-alignment): record what was handed
over without interrupting the host skill's interaction — no extra questions
unless the handed-over term is unusably vague. ADR *offers* queue until the
host skill's session closes; recording an already-accepted decision happens
immediately.

## File structure

Most repos have a single context: `docs/CONTEXT.md` with `docs/adr/` alongside it. A `CONTEXT-MAP.md` in `docs/` means multiple contexts; it points to where each one lives:

```txt
/
├── docs/
│   ├── CONTEXT-MAP.md
│   └── adr/                          ← system-wide decisions
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/                 ← context-specific decisions
│   └── billing/
│       ├── CONTEXT.md
│       └── docs/adr/
```

Create files lazily — only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved. If no `docs/adr/` exists, create it when the first ADR is needed.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Delegate focused term alignment

Use the `domain-term-alignment` skill (`../domain-term-alignment/SKILL.md`)
when the immediate problem is vocabulary mismatch rather than broader domain modeling.

Examples:

- The user and assistant may mean different things by the same term.
- The user uses two terms for what appears to be one concept.
- The user uses one term for what appears to be two concepts.
- Code, docs, tests, UI, APIs, or tickets use inconsistent names.
- The assistant introduced terminology that the user has not confirmed.

Mechanical rule: one ambiguous term resolvable in a single question →
handle it inline here; multiple entangled terms, or disagreement across
artifacts (code vs docs vs user) → delegate to `domain-term-alignment`. Either
way the write lands here: record the resolved term immediately if it is
project-specific and durable (durable = it will appear in code identifiers,
docs, or future conversations — not a one-off phrase for this discussion).

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"

### Update CONTEXT.md inline

When a term is resolved, update `CONTEXT.md` right there. Don't batch these up — capture them as they happen. Use the format in [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md), and this edit algorithm:

1. Search the file for the term AND for it appearing in any entry's
   `_Avoid_` line (it may already exist under another name).
2. Found as an entry → replace that entry's definition in place.
3. Found under another entry's `_Avoid_` → the concept exists; update that
   entry rather than adding a second one, and ask if the canonical name is
   changing.
4. New → insert alphabetically within its section (or the flat list).
5. Never leave two entries for one concept; re-read the file after the edit
   to confirm exactly one.

`CONTEXT.md` should be totally devoid of implementation details. Do not treat `CONTEXT.md` as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Offer ADRs sparingly

Offer an ADR only when the three criteria in
[ADR-FORMAT.md](./ADR-FORMAT.md) all hold (hard to reverse, surprising
without context, real trade-off — that file is the single authority on the
criteria, format, placement, and numbering). "Offer" means one line to the
user; write the ADR only on a yes.
