---
name: domain-term-alignment
license: MIT
metadata:
  version: 26-07-07-1
  upstream: https://github.com/mattpocock/skills
  provenance: Inspired by mattpocock/skills' ubiquitous-language / domain-modeling concept (MIT (c) 2026 Matt Pocock). Reworked here as a live-mismatch resolver; text is original.
description: Resolve live terminology mismatches — the user and assistant (or code, docs, tests, UI) using words differently. Use when the user asks "what should we call X", says "we keep using different words for this", wants naming/vocabulary/glossary questions settled, or when terms are ambiguous, overloaded, or inconsistent mid-discussion. For building or recording the domain model itself (CONTEXT.md, ADRs) use domain-modeling; do NOT use for mechanical rename refactors of implementation identifiers.
---

# Term Alignment

Make every important project-specific term mean one thing — to the user,
assistant, code, docs, tests, UI, and future maintainers. This skill
*resolves* mismatches; it **never writes `CONTEXT.md`** — recording goes
through the `domain-modeling` skill (`../domain-modeling/SKILL.md`), which
owns the file and its rules (including where the glossary lives and how to
read a CONTEXT-MAP).

## Procedure

1. **List candidate terms** from the conversation/artifact, each tagged with
   its mismatch signal: synonym drift, overload, near-synonym, legacy naming,
   assistant-introduced, or user–assistant / code–doc disagreement.
2. **Check before asking.** Grep each term and its suspected synonyms across
   the repo (including any `CONTEXT.md`) and compare hit sets. Unreachable
   tickets/UI are ask-the-user territory — say what you checked.
3. **One question at a time, always with a recommendation:**
   > You used `{Term A}` and `{Term B}`. I think these are one concept. I
   > recommend `{Term A}` as canonical, `{Term B}` under _Avoid_. Confirm?
   Never a bare "what should we call this?" unless no default exists.
4. **Hand off to `domain-modeling`** (read and follow
   `../domain-modeling/SKILL.md`) the moment a project-specific term
   resolves — canonical term, 1–2 sentence definition, avoided synonyms. Pass
   key-but-unresolved terms too, flagged, with the question that would settle
   them. Verify the entry landed; if that skill is unavailable, stop and
   report — never write the file yourself.
5. **Exit table:** term / canonical / status (recorded, unresolved-recorded,
   deferred-by-user). Every row is one of those three — nothing silently
   dropped.

## Rules

- **Stop on key-term instability.** Key = changing its meaning would change
  requirements, architecture, contracts, data shape, tests, permissions, or
  user expectations. Unsure → treat as key and ask. Don't design or build on
  an unstable key term.
- **Domain language, not implementation.** Implementation names appear only
  when they are the confusion source (legacy table/class names).
- **Don't over-glossarize.** Project-specific terms only; general programming
  vocabulary stays out. A term the user defers is recorded as deferred, not as
  an entry.
