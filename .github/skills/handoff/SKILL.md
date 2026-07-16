---
name: handoff
license: MIT
metadata:
  version: 26-07-08-2
  upstream: https://github.com/mattpocock/skills
  provenance: Adapted from mattpocock/skills (productivity/handoff, MIT (c) 2026 Matt Pocock). Fixed HANDOFF.md format, archive-before-overwrite and redaction grep added locally; Consumed-stamp lifecycle, consumed-aware overwrite, and fallback-only paste-block added locally; write triggers and the AGENTS.md resume block folded in from the deleted HANDOFF_RULES.md. Ported to Cursor (.github/skills, AGENTS.md).
description: Write docs/HANDOFF.md capturing session state (objective, branch, HEAD, files changed, commands run, test status, next action) so a fresh session can continue the work. Use when the user says handoff, pause, "new session", "pick this up later", or asks to save/transfer session state. Also self-invoke on observable triggers — a plan phase completes outside plan-tracked work, before a change touching >5 files, before an intentional model switch, or on noticing your own confusion (re-reading files already read, contradicting earlier conclusions) — never from a self-estimated token count.
---

Write a handoff document so a fresh agent can continue this work reading
nothing else. Fill every field from commands, not memory — if a command
can't produce the value, write `unknown`, never a guess.

## When to write one

On the user's word ("handoff", "pause", "new session") — or unprompted, on
any of these observable events. Never trigger on a guess about remaining
context: you cannot measure your own token usage.

- A plan phase completes (complex-plan-create plans record phase outcomes in
  their own phase docs and PLAN.md per the phase doc; this skill covers
  non-plan work).
- Before starting a large refactor or any change touching >5 files.
- Before an intentional model switch.
- Before compaction when you can see it coming (e.g. the user says they're
  about to compact).
- You observe yourself confused: re-reading files you already read this
  session, or contradicting a conclusion you reached earlier. Write the
  handoff first, then continue.

A handoff is cheap; a confused session is not. When unsure, write it.

## Where

`docs/HANDOFF.md` relative to the repo root (`git rev-parse --show-toplevel`;
no repo → current directory). Create `docs/` if missing.

If `docs/HANDOFF.md` already exists, check it for a `Consumed:` line:

- No `Consumed:` line → a live handoff nobody has picked up. Ask the user
  before replacing it; on yes, move it to `docs/HANDOFF-{YYYY-MM-DD-HHMM}.md`
  first, then write the new one. Never silently overwrite a live handoff.
- Has a `Consumed:` line → spent; overwrite it directly.

If a plan from the `complex-plan-create` skill is active (a `docs/plans/*/PLAN.md`
whose directory has no COMPLETED stamp), phase state belongs in that plan
itself — status in PLAN.md's phase table, detail in the phase docs — written
per the plan's own rules; let HANDOFF.md point there instead of duplicating.

## Format

This is just a proposed format, adapt according to the work. The goal is that
a fresh session can continue the work reading just this prompt/doc and the
docs it references.

```markdown
# HANDOFF — {objective, one line}

- Objective: {what the work is trying to achieve, 1-2 sentences}
- Repo: {absolute path}
- Branch: {git branch --show-current}
- HEAD: {git rev-parse --short HEAD}
- Dirty: {git status --short | wc -l} uncommitted paths

## Files changed
{git diff --name-status {base}..HEAD plus git status --short; one line each,
with a one-phrase why. State what {base} is.}

## Commands run + results
{only load-bearing ones: builds, tests, migrations, deploys — command,
exit/result, one line each}

## Test status
{exact command + observed result ("pytest -q → 42 passed"). "not run" is a
valid value; a guessed "passing" is not.}

## Assumptions
{numbered; things believed but not verified. "None."}

## Open questions
{numbered; decisions only the user can make. "None."}

## Next action
{ONE imperative action, concrete enough to start without reading anything
else. Not a list.}

## Paste into the fresh session (fallback only — see Rules)
    Read HANDOFF.md at {absolute path}. Continue from "Next action".
    Attach: {the 1-3 files the next action touches}.
```

A freshly written handoff has **no** `Consumed:` line — that absence is what
marks it live. The session that later continues the work adds
`Consumed: {YYYY-MM-DD}` under the title to retire it, per the resume rule
below.

## Plant the resume rule

The doc only works if the next session looks for it. After writing
HANDOFF.md, grep the repo-root `AGENTS.md` for `## Resuming a handoff`:

- Found → nothing to do; the doc will be picked up automatically.
- Missing → offer once: "Add the handoff resume rule to AGENTS.md so the
  next session picks this up on its own?" On yes, append the block below
  verbatim to the repo-root `AGENTS.md`, creating the file if missing. On
  no — or no repo, or the write fails — fall back to the paste-block.

(Cursor has no Claude Code–style global `~/.claude/CLAUDE.md` auto-load.
Optional: also add the same block to Cursor User Rules if you want it every
project; this skill only plants the repo `AGENTS.md`.)

```markdown
## Resuming a handoff

At session start, check for `docs/HANDOFF.md` (repo root):

- Missing → nothing pending; proceed with the user's request.
- Exists, no `Consumed:` line → a live handoff. Surface it and offer to
  continue from its "Next action" before other work — ask, don't hijack a
  session opened for something else.
- When you finish acting on it, add `Consumed: {YYYY-MM-DD}` under its
  title; the stamp, not deletion, is what retires it.
- Exists, already `Consumed:` → spent. Offer to delete it, then proceed.
```

## Rules

- Don't duplicate content already in other artifacts (plans, ADRs, PRDs,
  issues, commits) — verify each referenced path exists (`ls` it), then
  reference by path. A path you didn't verify doesn't go in.
- If the user passed arguments, add a `## Focus` section right under the
  title quoting them verbatim, and cut content irrelevant to that focus.
- Redact secrets, then verify with a runnable check — expect zero matches:
  `grep -nE '(api[_-]?key|secret|passw(or)?d|token)\s*[:=]|AKIA[0-9A-Z]{16}|-----BEGIN|Bearer [A-Za-z0-9._-]{20,}' docs/HANDOFF.md`
  Any hit: fix and re-run before finishing.
- The paste-block is a fallback, not the default. Skip it when the resume
  rule is in place — already found, or just planted per the section above.
  Print it otherwise (offer declined, no repo, write failed), so the next
  session still has a pointer. When unsure, print it.
- Optional `preCompact` transcript backup: wired in this repo via
  `.github/hooks.json` → `scripts/precompact_backup.py` (snippet also in
  `legacy/hooks-snippet.json`). Cursor's `preCompact` cannot inject
  preserve-instructions into compaction — model-side write triggers above
  remain the real preserve path; the hook is a transcript backstop + nudge.
