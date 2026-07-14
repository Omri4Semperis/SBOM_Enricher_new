---
name: ponytail-review
license: MIT
metadata:
  version: 26-07-08-1
  upstream: https://github.com/DietrichGebert/ponytail
  provenance: Adapted from DietrichGebert/ponytail (MIT (c) 2026 DietrichGebert). Diff-scoping, verified-replacement and net-line rules added locally; merged ponytail-audit's repo-wide scan pipeline, verified-delete grep, and ranking into this skill as a repo-scope mode (2026-07-07).
description: >
  Review for over-engineering only — either the current diff/PR/change, or
  the whole repo. Finds what to delete: reinvented standard library,
  unneeded dependencies, speculative abstractions, dead flexibility. One line
  per finding: location, what to cut, what replaces it. Use when the user
  says "review this diff/change/PR for over-engineering", "what can we cut
  from this change", "is this over-engineered", "audit this codebase for
  over-engineering/bloat", "what can I delete from this repo", "find bloat",
  or says "ponytail-review" / "ponytail-audit" (slash forms count too). For security/correctness/
  performance, or a full review, use full-review instead — this skill is
  complexity-only and applies no fixes.
---

Review for unnecessary complexity — nothing else. One line per finding:
location, what to cut, what replaces it. The best outcome is the target
getting shorter.

## Scope

Explicit `diff` or `repo` argument wins. Otherwise infer from phrasing:
"this diff/change/PR" → diff; "the codebase/repo/everything" → repo. Still
ambiguous and a diff exists (see below) → default to diff (the common case:
reviewing what's in front of you). Still ambiguous and no diff exists → ask
one question.

### Diff scope — acquire the diff

1. `git diff HEAD` (staged + unstaged).
2. Empty → `git diff $(git merge-base HEAD origin/main 2>/dev/null || git
   merge-base HEAD main)..HEAD` (the branch's own commits).
3. Still empty → print `no diff to review` and stop. Never fall back to
   reviewing whole files — that's what `repo` scope is for.

Line numbers are **new-file** line numbers; ranges `L<start>-<end>` allowed.

### Repo scope — scan pipeline

1. `git ls-files` (fallback: directory walk) — never read what it doesn't
   list. Skip `node_modules, vendor, third_party, dist, build, target, out,
   testdata`, lockfiles, minified/generated files (a
   `generated_or_vendored_detector.py` ships with the full-review skill if
   installed).
2. Read manifests first (`package.json`, `pyproject.toml`, `go.mod`, …) —
   every dependency is a candidate: does stdlib/platform cover it?
3. Grep-hunt, then read only the hits: single-implementation interfaces
   (`interface|abstract|ABC` then count implementors), factories with one
   product, wrappers that only delegate, files exporting one thing, flags
   and config keys (grep each key for readers), hand-rolled stdlib
   (`sleep.*retry|deep.?copy|left.?pad|parse.*query`, etc.).
4. Cap: more than ~200 source files → scan `src/` (or the main package)
   plus manifests only, and say so in the report header. Never silently
   sample.
5. Deferred debt: harvest the repo's `ponytail:` shortcut markers (run
   `ponytail_debt.py` from the full-review skill if installed, else
   `grep -rnI 'ponytail:' -- <scanned paths>`). These aren't deletion
   candidates — they're deferrals to revisit — so report them in a separate
   closing `Deferred debt` section, not among the tags: one line per marker
   (`<path>:L<line> — <ceiling>; upgrade: <trigger or NO TRIGGER>`), and a
   count of the no-trigger ones (the silent-rot risk). This is often the
   only pass that reads those markers back.

## Format

Always include the path (diffs and repos both commonly span multiple
files):

`<path>:L<line>: <tag> <what>. <replacement>. (-N lines)`

Tags (first match wins):

- `delete:` code whose replacement is literally nothing — dead code, unused
  flexibility, speculative feature. **Verify before tagging:** `grep -rn
  <symbol>` shows no non-definition references. Dynamic access possible
  (reflection, string keys) → tag `delete?:` and say why.
- `stdlib:` hand-rolled thing the standard library ships. Name the exact
  function and verify it exists (doc/REPL check) before claiming it —
  hallucinated replacements kill trust.
- `native:` dependency or code doing what the platform already does. Name
  the feature; same verification rule.
- `yagni:` abstraction with one implementation, config nobody sets, layer
  with one caller — code remains after inlining (if nothing remains, it's
  `delete:`).
- `shrink:` same logic, fewer lines. Show the shorter form (an indented
  one-line snippet under the finding is allowed).

## Examples

❌ "This EmailValidator class might be more complex than necessary, have you
considered whether all these validation rules are needed at this stage?"

✅ `auth.py:L12-38: stdlib: 27-line validator class. "@" in email, 1 line, real validation is the confirmation mail. (-26 lines)`

✅ `config.js:L4: native: moment.js imported for one format call. Intl.DateTimeFormat, 0 deps. (-1 line, -1 dep)`

✅ `repo.py:L88: yagni: AbstractRepository with one implementation. Inline it until a second one exists. (-15 lines)`

✅ `client.py:L52-71: delete: retry wrapper around an idempotent local call. Nothing replaces it. (-20 lines)`

✅ `util.py:L30-44: shrink: manual loop builds dict. dict(zip(keys, values)), 1 line. (-13 lines)`

## Scoring

`N` is always the sum of per-finding line counts — never a vibe.

- Diff scope: `net: -<N> lines possible.`
- Repo scope: `net: -<N> lines, -<M> deps possible.` (`M` = count of
  removable manifest dependencies named in findings), and rank findings
  dependency-removals first, then by `-N` descending, ties by path.

Nothing to cut, either scope: `Lean already. Ship.` and stop.

## Boundaries

Scope: over-engineering and complexity only. A correctness bug, security
hole, or performance problem noticed in passing: do not detail it — end the
report with one line, `out of scope: <n> correctness/security issues
noticed — run a full review (full-review)`. Never flag tests or asserts for
deletion; test bulk is out of scope here. One-shot: report and stop; applies
no fixes; no mode to turn off.
