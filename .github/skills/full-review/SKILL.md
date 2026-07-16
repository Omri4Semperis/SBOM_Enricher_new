---
name: full-review
metadata:
  version: 26-07-14-1
  provenance: Original to this library. Reads ponytail-review's over-engineering criteria at runtime; no upstream review-skill text copied.
description: Full code review of a diff/PR/change — correctness, security, maintainability, and operational risk — plus bundled census scripts for repo vitals. The over-engineering lens is delegated to ponytail-review and applied as one of the review's lenses. Use when the user asks to review code, review a diff/PR/changes, do a code review, do a full review, or check whether something is ready to merge. Language-agnostic. For a review that ONLY hunts over-engineering, use ponytail-review directly.
---

Review a change the way an experienced, skeptical senior dev does: practical,
optimizing for correctness, security, maintainability, testability, and
operational risk. Working code that will hurt to maintain gets rejected.

## Stance

The over-engineering lens is not re-derived here — it is ponytail-review's.
Read the sibling `../ponytail-review/SKILL.md` and apply its tags (`delete`,
`stdlib`, `native`, `yagni`, `shrink`) as review lenses over the diff,
folding whatever they surface into the verdict below (usually Should-fix or
Nits, occasionally a Blocker). If that file is absent, the fallback lens is
exactly this and nothing more: flag hand-rolled stdlib, a new dependency for
a few lines, custom code where a native feature exists, re-implementation of
a helper already in the codebase, abstractions with one implementation,
config for a value that never changes, vague names, oversized files, hidden
state, unnecessary indirection.

Whichever lens applies, two rules always hold:

- Never flag away: input validation at trust boundaries, error handling that
  prevents data loss, security measures, accessibility basics, the one
  runnable check ponytail requires non-trivial logic to leave behind.
- A fix must name its replacement ("use X from stdlib"), not just complain.

## Procedure

1. **Get the changeset.** `git diff HEAD`; if empty, `git diff
   $(git merge-base HEAD origin/main 2>/dev/null || git merge-base HEAD
   main)..HEAD`; if still empty and the user named no files, report "no diff
   to review" and stop — never silently fall back to reviewing whole files.
   Line numbers in findings are new-file line numbers.
2. **Native tooling first — its output is primary.** If the repo has
   configured linters, formatters, typecheckers, or tests (look for their
   config files), run them. Their failures are findings before you read a
   line. Never contradict or re-litigate what native tooling enforces.
3. **Census scripts — supplemental context only.** Run the bundled scripts
   (below) on the touched paths. They are census tools, not linters: they
   describe the terrain (sizes, churn, TODO load, risky constructs, test
   presence, generated files to skip, `ponytail:` deferrals) and never
   override native tooling or your own reading. Use
   `generated_or_vendored_detector` output to skip files a human wouldn't
   review. `ponytail_debt` is how deferred shortcuts get read back — surface
   any it finds in the touched files, and flag `[no-trigger]` ones as debt
   that will silently rot.
4. **Read the diff** (and only as much surrounding code as needed to judge
   it — callers of changed functions, tests of changed behavior).
5. **Verdict** in the format below, written to `./FULL-REVIEW.md` (see Output).

## Verdict format

```
## Executive summary <- one paragraph summary of the review, including what the changed code does, overall impression. Word hints to use: "LGTM", "needs work", "wrong approach", "security risk", "unmaintainable"; 

## Blockers        <- correctness, security, data loss; must fix

- path/file.py:42 — <one-line reason>

## Should-fix      <- will hurt to maintain; fix before or right after merge

- path/file.py:88 — <one-line reason>

## Nits            <- cheap improvements; author's call

- path/file.py:12 — <one-line reason>

## Census         <- Optional (see Output)

Verdict: approve | approve-with-changes | reject
```

Every item cites `file:line` and one line of reason naming the fix. Empty
sections stay in with "none". approve = no blockers, no should-fix;
approve-with-changes = no blockers; reject = any blocker, or should-fix
items that amount to "wrong approach".

## Output

Write the verdict to `./FULL-REVIEW.md` at the repo root, and also print it.
Full overwrite, regenerated from scratch each run — but if an existing
`./FULL-REVIEW.md` differs from something this skill would generate (it may
carry hand annotations), warn and confirm before overwriting. Append a
`## Census` section holding only the notable script rows (breaches and
anything that shaped the verdict), not full dumps. The scripts themselves
write nothing; redirect their stdout if you want raw TSV artifacts.

## Census scripts

`scripts/` — standalone python3 stdlib, deterministic sorted TSV/JSON on
stdout, exit 0 = clean / 1 = threshold breached / 2 = usage error, so they
are CI-usable. Run as `python scripts/<name>.py [paths] [flags]`. Every script
takes a `paths` positional (one or more files or directories, default `.`)
and, except where noted, skips common vendor/build dirs (`node_modules`,
`dist`, `.git`, …) and binary files. Scripts print to stdout only; the review
folds their notable rows into `./FULL-REVIEW.md` (see Output). To keep a raw
machine-readable copy, redirect: `python scripts/<name>.py … > out.tsv`.

### `file_lengths.py`

Counts lines in each text file and flags the long ones. `paths`: what to
scan. `--max-lines` (400): a file over this many lines is a breach. `--all`:
list every file, not just breaches. Returns TSV `lines<TAB>path` sorted by
line count desc; exit 1 if any file breaches.

Example: `python scripts/file_lengths.py src/ --max-lines 300`

### `long_lines.py`

Finds individual lines wider than a limit. `paths`: what to scan.
`--max-length` (160): a line longer than this many characters is a hit.
Returns TSV `path<TAB>line<TAB>length` sorted by path then line; exit 1 if
any hit.

Example: `python scripts/long_lines.py src/ --max-length 120`

### `largest_files.py`

Ranks files by byte size (binaries included, since big blobs are the point).
`paths`: what to scan. `--top` (20): how many to list. `--max-kb` (1024): any
file over this size in KiB is a breach. Returns TSV `bytes<TAB>path` for the
top N, sorted by size desc; exit 1 if any file breaches.

Example: `python scripts/largest_files.py . --top 10 --max-kb 512`

### `todo_scan.py`

Greps for `TODO`/`FIXME`/`HACK`/`XXX` markers. `paths`: what to scan.
`--max-count` (-1 = report-only): breach when total hits exceed this. Returns
TSV `path<TAB>line<TAB>tag<TAB>text` sorted by path then line; exit 1 only if
the count breaches.

Example: `python scripts/todo_scan.py src/ --max-count 50`

### `ponytail_debt.py`

Harvests `ponytail:` shortcut markers (the deliberate deferrals the ponytail
skill leaves behind, format `ponytail: <ceiling>, <upgrade trigger>`) into a
debt ledger — this is the review process that actually reads them back, so a
deferral can't quietly become permanent. `paths`: what to scan. `--max-count`
(-1 = report-only): breach when total markers exceed this. `--fail-on-no-trigger`:
breach if any marker names no upgrade path. Returns TSV
`path<TAB>line<TAB>upgrade<TAB>ceiling` sorted by path then line; markers with
no trigger show `[no-trigger]` and are the silent-rot risk. Skips `.md`
(the `#` marker collides with headings).

Example: `python scripts/ponytail_debt.py src/ --fail-on-no-trigger`

### `generated_or_vendored_detector.py`

Flags files a human wouldn't hand-review: vendored/build dirs,
minified/sourcemap/proto files, and files with a "generated" header marker
(walks everything but `.git`). `paths`: what to scan. `--fail-if-found`
(off): exit 1 when any such file is found instead of just reporting. Returns
TSV `reason<TAB>path` sorted by path.

Example: `python scripts/generated_or_vendored_detector.py . --fail-if-found`

### `test_presence_ratio.py`

Computes how much test code exists relative to source. `paths`: what to scan.
`--min-ratio` (0.1): breach when the test/source file ratio falls below this.
Returns one JSON object `{"ratio", "source_files", "test_files"}` (counts
disjoint); exit 1 if under ratio.

Example: `python scripts/test_presence_ratio.py src/ --min-ratio 0.2`

### `recent_changes.py`

Measures git churn (how often each file changed recently) from `git log`
output piped in on stdin — the script never runs git itself, so approving it
can't run an arbitrary command. **You run the git command; the user approves
it explicitly** (adjust `--since` for the window). The script only counts.
`--max-touches` (-1 = report-only): breach when any file's change count
exceeds this. Reads `git log --name-only --pretty=format:` on stdin; returns
TSV `touches<TAB>path` sorted by touches desc.

Example: `git log --since="14 days ago" --name-only --pretty=format: | python scripts/recent_changes.py --max-touches 10`

### `risky_patterns.py`

Scans for risky constructs by regex, patterns loaded from a JSON config.
`paths`: what to scan. `--config` (defaults to `risky_patterns.json` beside
the script): the pattern set. `--max-count` (-1 = report-only): breach when
total hits exceed this. Returns TSV `name<TAB>path<TAB>line<TAB>text` sorted
by path, line, name; hits are review pointers, not verdicts (expect false
positives).

Example: `python scripts/risky_patterns.py src/ --config .review/risky_patterns.json --max-count 0`

Add repo-specific risky patterns by pointing `--config` at a project-local
JSON — never by editing code.

## Boundaries

- Census numbers inform judgment; they are not findings by themselves. A
  500-line file is a finding only if the diff made it worse or touching it
  was avoidable.
- Out-of-scope observations (product ideas, unrelated refactors): one line
  at the end, "out of scope: …", nothing more.
- One-shot: review, write `./FULL-REVIEW.md`, done. Applies no fixes unless
  the user asks.
