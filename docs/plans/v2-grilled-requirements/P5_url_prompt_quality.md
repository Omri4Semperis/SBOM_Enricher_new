# P5: url_prompt_quality

**Plan:** v2 grilled requirements — deliver the five 2026-07-19 signed-off
requirements for the SBOM Enricher. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** Write freely here during implementation. Your only other
editable file is `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other phases' blocks); never another phase's `P*` doc.

**Demo:** `license_prompt(...)` returns text that demands the component's own
published, holder-bearing license/copyright file, forbids canonical/boilerplate
license text, offers an AUTHORS/NOTICE/COPYRIGHT fallback, and includes the
`.lesserv3`→`AUTHORS` worked example.

**Goal:** Implement requirement E from ADR 0015. A prompt-only
change (no new detection code) that strengthens the `license_code_url` guidance
so Claude more reliably returns a URL to the component's OWN license/copyright
file that names a concrete holder — the meaning locked in `docs/CONTEXT.md`
under **Inferred License Code URL** — rather than boilerplate license text.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] No dependencies (independent)
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥157 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

Requirement E (from ADR 0015; detail in
`docs/archive/DECISIONS_2026-07-19_grilled-requirements.md` §E):

- E1: prompt-only fix — NO new detection/parsing code.
- E2: strengthen the license-URL prompt to:
  1. demand the component's OWN published license/copyright file (its repo or
     package platform) that names a specific holder FOR THIS component;
  2. forbid canonical/boilerplate license text (e.g. the full LGPLv3 legalese
     that names no holder);
  3. include the nettle worked negative example: a package whose standard
     LICENSE was LGPLv3 boilerplate (`.lesserv3`) so the holder lived in the
     `AUTHORS` file — prefer `AUTHORS` there;
  4. fall back to `AUTHORS`/`NOTICE`/`COPYRIGHT` when the standard LICENSE is
     boilerplate;
  5. stay deliberately not-too-strict — do NOT add a hard "must be a repo"
     rule.

The meaning to encode is the CONTEXT definition of **Inferred License Code
URL**: "a reachable, downloadable URL to the component's OWN license/copyright
file … that names a concrete copyright holder for it. NOT the
canonical/boilerplate text of the license itself." Keep it consistent with that
wording.

Code to change — `src/prompts.py`, `license_prompt(purl, lib_name, version) ->
tuple[str, dict]`. The current `license_code_url rules:` bullets are:

- must serve raw license text (not an HTML viewer, not a registry archive);
- pin to the release tag / commit SHA for this version (not main/master/HEAD);
- avoid generic template pages (spdx.org, opensource.org, choosealicense, …);
- if no project file can be found → empty string.

Keep those, and ADD the E2 guidance (own-holder file preference,
boilerplate-forbidden, AUTHORS/NOTICE/COPYRIGHT fallback, the `.lesserv3`
example). Do NOT weaken the existing raw-URL / pin-to-version / avoid-template
rules. `LICENSE_SCHEMA` is unchanged (still `license_name`, `license_code_url`,
`reasoning`).

Testing note: this is an LLM prompt, so the deterministic, offline-safe check
is on the prompt STRING, not on model behavior. Add a small
`tests/test_prompts.py` asserting the returned prompt text contains the new
guidance (case-insensitive substring checks for e.g. "holder", "boilerplate",
"AUTHORS", "NOTICE", and that it still mentions raw + not main/master/HEAD).
There is currently no prompts test file — create one.

Gotcha: keep the prompt a single f-string block as today; don't restructure the
function or its return type. Watch the closing `"""` and the trailing "No
markdown fences." line.

## Files

**Touch (complete list):**

- `src/prompts.py` — edit: extend the `license_code_url rules:` section of
  `license_prompt` with the E2 guidance.
- `tests/test_prompts.py` — create: substring assertions on `license_prompt`
  output (new guidance present; existing rules retained).

**Do not touch:** the copyright prompts, equality prompts, and schemas in
`prompts.py` (E is license-URL only), any `src/` module other than
`prompts.py`, and anything not listed under Touch. Needing an unlisted file
means the plan is wrong: note it here + a comment in your `PLAN.md` block; if
blocked, follow **If blocked**.

## Tasks

### T1: strengthen the license-URL prompt

- Steps: in `license_prompt`, extend the `license_code_url rules:` bullets to
  add, in plain imperative bullets:
  - prefer the component's OWN published license/copyright file (its repo or
    package platform) that names a concrete holder for THIS component;
  - do NOT return canonical/boilerplate license text that names no holder
    (e.g. the full LGPL/Apache legalese);
  - when the standard LICENSE/COPYING is generic boilerplate, prefer an
    `AUTHORS`/`NOTICE`/`COPYRIGHT` file that carries the holder;
  - worked example: for a package whose LICENSE was LGPLv3 boilerplate
    (`.lesserv3`), the holder was in `AUTHORS` — return that;
  - (keep it not-too-strict: a repo is preferred, not mandatory).
  Keep every existing bullet.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_prompts.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: prompt-content test

- Steps: create `tests/test_prompts.py`; import `license_prompt` (the test
  suite puts `src/` on the path via `conftest.py`). Call it with a sample purl
  and assert (case-insensitive) the text contains the new guidance
  ("holder", "boilerplate" or "canonical", "AUTHORS", "NOTICE") AND still
  contains the retained rules ("raw", "main/master/HEAD"). One test function is
  enough.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_prompts.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. No separate typecheck/lint in this repo — step 1 covers it.
3. Fresh review: the diff `git diff {baseline}..HEAD` (baseline from `PLAN.md`)
   is reviewed against this doc plus an over-engineering lens by a context that
   did not implement it (subagent given only the diff, this doc, and the lens;
   if unavailable, stop and ask the user to review in a new session). Fix
   findings, re-run 1 — but a lens finding on something this doc explicitly
   ordered (prompt-only; the `.lesserv3` example) is NOT fixed; record it as a
   note here.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_prompts.py -q` → exit 0,
  all passed.
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.

## Anti-goals

Do not, even if it seems better:

- No new detection/validation code (E1) — prompt text only.
- No hard "must be a repo" rule (E2.5).
- No change to `LICENSE_SCHEMA` or the function signature/return type.
- No edits to copyright/equality prompts.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list, do not edit another
phase's doc. To abandon work already done, roll back with
`git reset --hard {baseline hash from PLAN.md's phase table}`.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (the start
   hash) and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block.
   Keep it short; write the full detail below and point to it.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: {phase goal, one line}
HEAD: {git rev-parse --short HEAD} | Branch: {git branch --show-current}
Files changed: {git diff --name-only <baseline>..HEAD output}
Commands run: {the Verify/gate commands and their observed results}
Test status: {suite command + observed result}
Assumptions: {numbered, or "none"}
Open questions: {numbered, or "none"}
Next action: {the next eligible phase per PLAN.md's table, or "plan complete"}
```
