# P3: copyright_honesty

**Plan:** fact-grade-first tranche — make the audit measurement truthful without
gaming the headline number. This phase stops the agent emitting a wrong copyright
holder; read `PLAN.md`'s Goal and Context in full before starting.

**Your workspace.** This doc is writable: record decisions, dead ends, and
findings here during implementation. The other file you may edit is `PLAN.md`
(your table row, your Phase-notes block, and Incoming comments in other blocks).
Never edit another phase's `P*` doc. Status lives in `PLAN.md`'s table.

**Demo:** when the LICENSE text yields only a known stray/generic upstream holder
(e.g. "The Go Authors") for an unrelated package, `resolve_copyright` returns
`UNKNOWN` instead of that wrong holder — shown by
`pytest tests/test_copyright.py -k denylist -q`.

**Goal:** Two narrow copyright fixes from DECISIONS branches F and D.
(F) Add a **reject-only** guard to the copyright chain: a small denylist of known
stray/generic upstream holders causes that extracted holder to be dropped, so the
chain falls through to `UNKNOWN` rather than emitting the wrong name. The guard is
**asymmetric** — it never requires the holder to match the package/repo owner.
(D) Tighten the judge copyright prompt: small year tolerance (not year-blindness)
and directional same-class "and others"/"and Contributors" handling.

## Entry criteria

Run each; all must hold before other work. If any fails, follow **If blocked**.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0 (`119 passed`, or higher if earlier phases merged — P3 has no dependency)
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

`src/copyright.py`:
- `resolve_copyright(license_text, purl, lib_name, version, model)` is the chain:
  `extract_copyright(license_text)` (GPT-4.1 file read) → if UNKNOWN, npm author
  (`_npm_author_copyright`) → if None, `infer_copyright_web` → else `_unknown(...)`.
  Each step returns `{"copyright": ..., "reasoning": ...}`; `_unknown(reason)`
  builds `{"copyright": "UNKNOWN", "reasoning": reason}`.
- `extract_copyright` already rejects placeholder templates via
  `_is_placeholder_copyright` (regex `_PLACEHOLDER_TOKEN_RE`). The new denylist is
  a sibling reject test, but for *specific stray real holders*, not templates.
- Tests monkeypatch `copyright_mod.extract_copyright`, `_npm_author_copyright`,
  and `infer_copyright_web`, then assert the resolved copyright/reasoning and
  `meta.billable_calls`. Follow that style; no live calls.

Where the guard goes (ponytail — one guard, all callers): the wrong holder can
come from either the file extraction or the web inference. Put a single helper
`_is_stray_holder(text) -> bool` (module-level, a small frozenset of lowercased
denied phrases + substring match) and apply it at the two points where a
concrete holder is about to be accepted in `resolve_copyright`: after
`extract_copyright` returns non-UNKNOWN, and after `infer_copyright_web` returns a
holder. On a stray match, treat that source as UNKNOWN and continue the chain
(file→npm→web) rather than returning it. Do **not** add it inside
`extract_copyright` itself (keep that function's contract as "what the file says";
the *policy* of rejecting strays is the resolver's job).

Denylist seed (DECISIONS F): "The Go Authors", "The Android Open Source Project".
Keep it tiny and additive; match case-insensitively as a substring of the holder.

`src/prompts.py`:
- `EQUALITY_JUDGE_SYSTEM` is the shared judge system prompt (used by name,
  copyright, and URL judges) — do **not** loosen it globally.
- `equality_copyright_prompts(inferred, ground_truth)` builds the copyright judge
  user message. The two new rules (year tolerance; directional same-class extra
  holders) go **here**, scoped to copyright only, as explicit user-message
  guidance — never a general "be lenient" instruction (DECISIONS branch I #1: this
  is the one risk that threatens the truth goal; keep it rule-scoped).

## Files

**Touch (complete list):**

- `src/copyright.py` — edit: add `_STRAY_HOLDERS` frozenset + `_is_stray_holder`
  and apply it in `resolve_copyright` (reject-only, asymmetric).
- `src/prompts.py` — edit: extend `equality_copyright_prompts` with the two narrow
  rules (copyright judge only).
- `tests/test_copyright.py` — edit: assert stray holder → UNKNOWN and that a
  normal (non-denied) holder is untouched.

**Do not touch:** `EQUALITY_JUDGE_SYSTEM` (shared — no global loosening),
`extract_copyright`'s return contract, the npm/web fallback internals beyond
inserting the reject check, and anything not listed above. Needing an unlisted
file means the plan is wrong: record it here and in your `PLAN.md` block; if you
can't proceed, follow **If blocked**.

## Tasks

### T1: Reject-only stray-holder guard in `resolve_copyright`

- Steps:
  - Add module-level `_STRAY_HOLDERS = frozenset({"the go authors", "the android
    open source project"})` and `_is_stray_holder(text) -> bool` (lowercase the
    input, return True if any denied phrase is a substring).
  - In `resolve_copyright`: after `extract_copyright` returns a non-UNKNOWN
    copyright, if `_is_stray_holder(file_data["copyright"])`, skip it (fall through
    to the npm/web steps) instead of returning it. After `infer_copyright_web`
    yields a holder, if `_is_stray_holder(copyright_text)`, return
    `_unknown("stray upstream holder")` instead of accepting it.
  - Never add a "holder must match package/repo owner" check (asymmetric guard).
- Verify: add `test_resolve_denylist_stray_holder_file` — `extract_copyright`
  returns `{"copyright": "Copyright (c) 2019 The Go Authors", ...}`, npm and web
  both return None/UNKNOWN; assert resolved `copyright == "UNKNOWN"`. Add
  `test_resolve_keeps_normal_holder` — a normal holder like
  "Copyright (c) 2020 John-David Dalton" is returned unchanged (guards against a
  match-requirement regression).
  `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -k "denylist or normal_holder" -q` → exit 0.
- Commit when green.

### T2: Tighten the copyright judge prompt

- Steps: extend the user message built by `equality_copyright_prompts` with two
  short, explicit rules, copyright-only:
  (a) year tolerance — when the holder matches, a small year difference (≈1–2
  years) is the same notice; do not blanket-ignore years, large/clearly different
  ranges are not automatically equal.
  (b) directional same-class extra holders — "and Contributors"/"and others" is
  equal only when it is the same class of holder enumerated more fully AND the
  *inferred* side is the more elaborate one (inferred ⊇ ground_truth is fine;
  ground_truth ⊇ inferred is not automatically equal); a different class of
  contributor added is not equal.
- Verify: add `test_copyright_prompt_has_year_and_directional_rules` in
  `tests/test_copyright.py` (or extend an existing prompt test) asserting the
  built user string contains the year-tolerance and directional cues (e.g. the
  substrings `year` and `and Contributors`/`and others`). This is a deterministic
  content check; the live ~21-pair re-judge is the opt-in spot-check below.
  `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -q` → exit 0.
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, baseline `+ new tests` passed
2. Fresh review of `git diff <baseline>..HEAD` (baseline = hash in `PLAN.md`)
   against this doc + an over-engineering lens, by a context that didn't implement
   it (subagent given only the diff, this doc, the lens; if unavailable, ask the
   user to review in a new session). Fix findings, re-run 1 — but a lens finding on
   something this doc explicitly ordered (the two prompt rules) is NOT fixed;
   record it here.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -k denylist -q` → exit 0, ≥1 passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -q` → exit 0 (chain unbroken)
- Opt-in (needs Azure creds; not required to accept): targeted re-judge of the
  ~21 flagged copyright pairs from the frozen run confirms no over-correction.
  If run, record counts here; if skipped, note "deferred to P4 / opt-in".

## Rollback

To abandon: `git reset --hard <baseline hash from PLAN.md>`, then set Status to
`blocked` in `PLAN.md` with a one-line reason in your Phase-notes block.

## Failure modes

1. A correct copyright starts becoming UNKNOWN → your guard is not asymmetric;
   confirm it only rejects on a denylist substring match, never on a
   holder≠owner comparison. `test_resolve_keeps_normal_holder` catches this.
2. The judge becomes generally lenient (year-blind, all "and others" equal) →
   you loosened `EQUALITY_JUDGE_SYSTEM` or dropped the directionality; keep the
   rules in `equality_copyright_prompts` and directional.

## Anti-goals

Do not, even if it seems better:

- No positive NOTICE/source-header copyright extraction (deferred — `docs/DEFERRED.md`).
- No "holder must equal package/repo owner" requirement — it would wrongly nuke
  hundreds of correct copyrights.
- No global loosening of the shared judge system prompt.
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here" fixes.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (start hash)
   and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: {phase goal, one line} | HEAD: {short hash} | Branch: {name}
Files changed: {git diff --name-only <baseline>..HEAD}
Commands + Test status: {gate commands and observed results}
Assumptions / Open questions: {numbered, or "none"}
Next action: {next eligible phase per PLAN.md, or "plan complete"}
```
