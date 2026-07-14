---
name: repo-assistant-setup
metadata:
  version: 26-07-08-1
  provenance: Original to this library. Ported to Cursor (.cursor/skills, AGENTS.md, .cursor/hooks.json).
description: Inspect a repository and propose a minimal set of persistent assistant assets (ARCHITECTURE.md, module map, DEVELOPMENT.md, TESTING.md, AGENTS.md, at most two repo-specific skills). Use when the user asks to set up a repo for AI assistants or agents, bootstrap or improve AGENTS.md or CLAUDE.md, add assistant docs, make a codebase agent-friendly, or onboard an assistant to a new repository.
disable-model-invocation: true
---

Set up a repository so assistants work well in it. Three steps, in order.
Nothing is written to the repo before step 3.

## 1. Inspect

First, confirm git: `git rev-parse --is-inside-work-tree`. If the repo has no
git, stop and strongly urge the user to `git init` before continuing —
without it the assistant assets are half-blind: no history to find hot areas,
no baseline hashes for the maintenance stamp, and skills like git-hygiene and
the plan drift-check have nothing to read. Offer to run `git init` for them;
proceed on a non-git repo only if they decline, and note in the proposal
which assets will be weaker for it.

Bounded pass — read, don't explore endlessly:

- `README*`, existing `AGENTS.md`/`CLAUDE.md`/`CONTRIBUTING.md`/docs dir.
- Build/tooling manifests (`package.json`, `pyproject.toml`, `Makefile`,
  CI config) — how it builds, tests, lints, deploys.
- Top two directory levels; the 3–5 largest/most-changed source dirs
  (`git log --since="90 days ago" --name-only` for hot areas).
- Test layout: where tests live, how they run.

## 2. Propose — do not create

Present a proposal table and stop for approval. Do not write any file, even
a draft, before the user approves. For each proposed asset: name, one-line
purpose, one-line justification tied to something found in step 1. Omit any
asset the repo doesn't earn — an empty proposal ("this repo needs nothing")
is a valid outcome.

Preference order (propose the earliest items that suffice, not all of them):

1. `ARCHITECTURE.md` — high-level: what the system is, main components, how
   data flows. Only if the repo is big enough that reading code doesn't
   reveal this in minutes.
2. A module/detail map — per-directory one-liners. Only for repos with many
   top-level modules.
3. `DEVELOPMENT.md` — build, run, debug commands that actually work.
4. `TESTING.md` — how to run and write tests, only if non-obvious.
5. `AGENTS.md` — assistant-specific rules; keep it short and point at the
   files above rather than duplicating them. (Prefer `AGENTS.md` over
   Claude-only `CLAUDE.md`; if a `CLAUDE.md` already exists and is maintained,
   propose updating it *or* migrating content into `AGENTS.md` — don't create
   both with duplicated rules.)

Repo-specific skills: only for a **repeated, non-obvious** workflow
(a multi-step release dance, a code-gen ritual). Maximum 2 unless the
proposal explicitly justifies more. A workflow used once, or derivable from
`DEVELOPMENT.md`, is not a skill.

One ready-made repo skill ships with this skill:
[templates/git-hygiene/](templates/git-hygiene/) — warns when junk
(build artifacts, logs, secrets, oversized files) is staged or tracked and
maintains a per-repo allowlist. Propose it when the repo's git status/history
shows that pain. Install = copy the whole template directory to
`<repo>/.cursor/skills/git-hygiene/` and merge its `hooks-snippet.json` into
`<repo>/.cursor/hooks.json` (create with `"version": 1` if missing). It stays
a TEMPLATE here (never a directory directly under `~/.cursor/skills/`): a
personal skill overrides same-named project skills, so a global copy would
shadow every repo's local allowlist.

Do not propose documenting what the code already states cheaply (file lists,
dependency versions, function inventories) — stale copies are worse than
nothing.

## 3. Generate approved drafts

Only the approved subset. Every generated asset embeds, near the top,
this maintenance rule **verbatim**:

> When a commit changes architecture, public APIs, build, test strategy,
> deployment, or conventions, update this file in the same commit.

followed by a verification line the agent bumps whenever it confirms the
file still matches reality:

> Last verified: <commit hash>

Fill `<commit hash>` with the current `git rev-parse --short HEAD`.
Keep each draft short; a file nobody maintains is debt, and the shorter it
is the more likely the maintenance rule gets followed.
