---
name: git-hygiene
metadata:
  version: 26-07-14-1
  provenance: Original to this library.
description: Scan git for files that shouldn't be tracked — build artifacts (__pycache__, node_modules, dist), logs, temp/editor files, secrets (.env, keys), oversized files — and propose .gitignore fixes. Use when the user asks to interact with git, to check tracking or .gitignore, says "unwanted files", "why is X tracked", "clean up git tracking", after the git-hygiene commit hook blocks a commit, or when wrapping up work that added files.
---

Warn about files git is tracking (or about to track) that probably don't
belong, propose `.gitignore` entries, and remember the user's verdicts in
this skill's own `rules.json` — this skill is repo-local precisely so those
verdicts stay per-repo.

## Procedure

1. **Scan.** The scanner reads candidate files on stdin as `kind<TAB>path`
   lines — it never runs git itself, so the user approves the read-only git
   commands, not a script that could run anything. Run these three (all
   read-only), label each output line with its kind and a tab, and pipe the
   combined stream in:
   - `staged`    ← `git diff --cached --name-only`
   - `tracked`   ← `git ls-files`
   - `untracked` ← `git ls-files --others --exclude-standard`

   PowerShell example (run from this skill's directory, or use the absolute
   path to `scripts/git_hygiene_scan.py` next to this SKILL.md):
   ```
   & {
     git diff --cached --name-only | % { "staged`t$_" }
     git ls-files | % { "tracked`t$_" }
     git ls-files --others --exclude-standard | % { "untracked`t$_" }
   } | python scripts/git_hygiene_scan.py
   ```
   bash example:
   ```
   { git diff --cached --name-only | sed 's#^#staged\t#'
     git ls-files | sed 's#^#tracked\t#'
     git ls-files --others --exclude-standard | sed 's#^#untracked\t#'
   } | python scripts/git_hygiene_scan.py
   ```
   Exit 0 = clean; 1 = findings (TSV `kind rule path`); 2 = config error
   (report it, stop). Kinds: `staged` (about to be committed — most urgent),
   `tracked` (already committed), `untracked` (future accident; gitignore
   candidate).
2. **Clean case — say so, one line:** "Git-tracking scan LGTM —nothing
   unwanted staged or tracked; `.gitignore` seems well configured."
   Then stop. (The point is the user knows the check ran.)
3. **Findings — group by rule and propose,** one numbered item per rule
   (not per file), each with: the matched files (count + up to 3 examples),
   the proposed `.gitignore` line(s), and — for `tracked` files — the
   untrack command, since `.gitignore` alone never untracks:
   `git rm -r --cached <path>` (files stay on disk). Prefer directory
   patterns (`__pycache__/`) over per-file ones. **Secrets** (`secret:*`
   rules): lead with them, and add that already-committed secrets remain in
   git history — rotating the credential is the real fix, history rewriting
   is the user's call. All in plain English, explaining meaning and implications.
4. **Wait for the user's verdicts.** Apply exactly what's accepted:
   - Accepted → append the lines to `.gitignore` (create if missing; append
     under a `# git-hygiene` marker comment, never rewrite the user's
     existing entries), and run the untrack commands for tracked files.
   - Rejected ("kind X should be tracked") → append to `rules.json`'s
     `allow` array: `{"pattern": "<glob>", "why": "<user's reason>",
     "date": "<YYYY-MM-DD>"}`. That kind is never warned about again.
     Exception: a `secret:` finding is allowed per-path, never per-kind —
     `*.key` as a class stays warnable.
5. **Re-run the scan** and show the one-line result (clean, or what remains).

## Self-editing rules

- The `allow` array in `rules.json` is the ONLY thing this skill edits about
  itself. Warn lists and `max_kb` change only when the user explicitly asks.
- Never edit `rules.json` without a user verdict to record.

## Notes

- This repo wires the hook in `.github/hooks.json` (`beforeShellExecution`).
  It blocks agent-made `git commit`s when junk is staged and points here.
  Guards only agent commits — the user's own terminal commits bypass it.
  The hook is the one place the scanner runs git itself (read-only, fixed
  args, no shell). Model-side procedure above remains the guarantee if hooks
  are disabled.
- Scripts report; the agent edits. `.gitignore` and `rules.json` are only
  ever written through steps 4's rules.
