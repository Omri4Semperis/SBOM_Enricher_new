# P2: association_aware_holder

**Plan:** fact-grade-review-fixes — clear every review finding so the
fact-grade tranche signs off. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** Write freely here during implementation. Your only other
editable file is `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other phases' blocks); never another phase's `P*` doc.

**Demo:** `pytest tests/test_copyright.py -q` is green with two new tests: a
`pkg:golang/` package that carries "The Go Authors" keeps that copyright,
while a non-Go package carrying "The Go Authors" is rejected as a stray holder.

**Goal:** Fix S1 — replace the holder-only stray denylist with an
association-aware guard that rejects a stray holder only when the package is
NOT of that holder's family, passing package context (`purl`/`lib_name`) into
the predicate. Record the decision as ADR 0007 (required by the user).

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] No dependencies to check (this phase depends on nothing)
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, 130 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

`src/copyright.py` — copyright resolution. Key facts for this phase:

- `_STRAY_HOLDERS = frozenset({"the go authors", "the android open source project"})`
  (line ~32) and `_is_stray_holder(text: str) -> bool` (line ~35) which lowercases
  `text` and returns True if any stray phrase is a substring. **The bug:** it has
  no package context, so it rejects "The Go Authors" even for a legitimate
  `pkg:golang/` component, and AOSP for a legitimate Android component.
- Callers of `_is_stray_holder`, all in `resolve_copyright` (line ~126):
  - line ~135: `if file_data["copyright"].upper() != "UNKNOWN" and not _is_stray_holder(file_data["copyright"]):`
  - line ~152: `or _is_stray_holder(copyright_text)` (inside the web-result reject test)
  - line ~154: `if copyright_text and _is_stray_holder(copyright_text):` (to pick the reject reason)
- `resolve_copyright(license_text, purl, lib_name, version, model)` already
  has `purl` and `lib_name` in scope — pass them straight into the new
  predicate. No new plumbing needed.
- The other in-repo caller is `ad_hoc_scripts/analysis/rescore.py` — **do not
  edit it here** (P3 owns it). Leave an Incoming comment in P3's `PLAN.md` block
  with the exact new signature so P3 can update its call.

Design for the new guard (settled in grilling): make it per-holder, each rule
carrying its own matcher for "is this package of that family":

- "the go authors" → stray only when the purl is NOT `pkg:golang/...`.
- "the android open source project" (AOSP) → allowed only when the purl or
  `lib_name` carries a known Android marker (e.g. the substring `android`);
  otherwise stray.

So the predicate signature becomes association-aware, e.g.
`_is_stray_holder(text: str, purl: str = "", lib_name: str = "") -> bool`.
Keeping `purl`/`lib_name` keyword-defaulted means a bare `_is_stray_holder(text)`
still parses (returns the association-unaware verdict) — but P3 will pass the
context explicitly. Record the chosen exact signature in the Outcome.

Tests: `tests/test_copyright.py` uses `monkeypatch` and
`asyncio.run(copyright_mod.resolve_copyright(...))`. Existing guard tests to
mirror: `test_resolve_denylist_stray_holder_file`, `test_resolve_keeps_normal_holder`,
`test_resolve_denylist_stray_holder_web`.

## Files

**Touch (complete list):**

- `src/copyright.py` — edit: rewrite `_is_stray_holder` to be association-aware
  (per-holder rules) and update its three call sites in `resolve_copyright` to
  pass `purl`/`lib_name`.
- `tests/test_copyright.py` — edit: add two tests (legit Go holder kept; stray
  Go association on a non-Go package rejected). Optionally an AOSP pair.
- `docs/adr/0007-association-aware-stray-holder.md` — create: record the
  decision (required).

**Do not touch:** `src/download.py` (P1 owns it),
`ad_hoc_scripts/analysis/rescore.py` (P3 owns it), and anything not listed
under Touch. Needing an unlisted file means the plan is wrong: record it as a
note in this doc and a comment in your `PLAN.md` block; if the phase can't
proceed without it, follow **If blocked**.

## Tasks

### T1: Rewrite `_is_stray_holder` to be association-aware

- Steps: Replace the holder-only `_STRAY_HOLDERS`/`_is_stray_holder` with a
  per-holder rule structure. Each rule = a lowercased holder phrase + a
  predicate `is_of_family(purl, lib_name) -> bool`; the holder is stray when its
  phrase is present in `text` AND the package is NOT of that family. New
  signature: `_is_stray_holder(text: str, purl: str = "", lib_name: str = "") -> bool`.
  Rules:
  - "the go authors": family = `purl.strip().lower().startswith("pkg:golang/")`.
  - "the android open source project": family = the substring `"android"`
    appears in `purl.lower()` or `lib_name.lower()`.
  Return True if any rule's phrase is present and its family predicate is False.
- Update the three call sites in `resolve_copyright`: line ~135, ~152, ~154 —
  pass `purl` and `lib_name` (both in scope) into each `_is_stray_holder(...)`
  call.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -q` → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: Tests — legit family kept, stray association rejected

- Steps: Add `test_resolve_keeps_go_authors_for_golang_purl(monkeypatch)`: a
  LICENSE text yielding "The Go Authors" with `purl="pkg:golang/..."` resolves
  to that copyright (not rejected), mirroring
  `test_resolve_file_success_skips_fallbacks`. Add
  `test_resolve_rejects_go_authors_for_non_go_purl(monkeypatch)`: the same
  holder with a non-Go purl (e.g. `pkg:npm/...`) still triggers the guard and
  falls through to the fallback chain / `UNKNOWN` — mirror
  `test_resolve_denylist_stray_holder_file`. (Optional AOSP pair if quick.)
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -q` → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T3: ADR 0007 — record the association-aware decision

- Steps: Create `docs/adr/0007-association-aware-stray-holder.md` following the
  house style of `docs/adr/0006-unscoreable-grade.md`. Decision: *a generic
  upstream holder ("The Go Authors", AOSP) is only rejected as stray when the
  package is not of that holder's family (purl/lib_name), because a holder-only
  denylist cannot tell a legitimate Go/Android component from a misattributed
  one.* Rejected alternatives: (a) holder-only denylist (the bug — rejects
  legitimate Go/Android packages), (b) removing the guard entirely (reopens the
  misattribution the tranche added it to close). Note the guard stays
  reject-only — it never turns a Mismatch into a Hit. Keep under ~40 lines.
- Verify: `.\.venv\Scripts\python.exe -m py_compile src/copyright.py` → exit 0,
  and the ADR file exists with `status: accepted` front-matter.
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥132 passed (130
   baseline + 2 new tests).
2. No typecheck/lint tool is configured in this repo; skip.
3. Fresh review: the diff `git diff {baseline}..HEAD` (substitute the hash
   recorded in `PLAN.md` at phase start) is reviewed against this doc plus an
   over-engineering lens by a context that did not implement it (subagent given
   only the diff, this doc, and the lens; if subagents are unavailable, stop and
   ask the user to review in a new session). Fix findings, re-run 1. A lens
   finding on something this doc explicitly ordered (the ADR, the per-holder
   rule structure) is NOT fixed; record it as a note here.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -q` → exit 0, all passed (includes the 2 new tests).
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥132 passed.

## Anti-goals

Do not, even if it seems better:

- No general "package family" framework — two hardcoded rules (Go, AOSP) is the
  whole requirement. Do not add a registry, config, or plugin system.
- Do not touch `rescore.py` (P3 updates its call) or `download.py` (P1).
- Do not change the fallback chain order in `resolve_copyright`; only the
  guard's association-awareness changes.

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
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block
   — **record the exact final `_is_stray_holder` signature** so P3 can update
   its call; confirm the seeded Incoming comment to P3 still holds.
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
