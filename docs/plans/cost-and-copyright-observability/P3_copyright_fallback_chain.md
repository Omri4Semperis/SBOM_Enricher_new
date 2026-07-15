# P3: copyright_fallback_chain

**Plan:** cost-and-copyright-observability — make the enricher's spend real and
its copyright coverage complete. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** This doc is writable: record whatever detail you need here.
The other file you may edit is `PLAN.md` — your row in the phase table, a
concise reflection in your own Phase-notes block, and **Incoming comments** in
*another* phase's block when you discover something it must know. You never edit
another phase's `P*` doc. Status is tracked in `PLAN.md`'s table.

**Demo:** a component whose LICENSE file yields no copyright but whose npm
registry lists an `author` (or whose holder is only findable on the web) gets
`inferred_copyright` filled from the fallback instead of `UNKNOWN`; the story
shows the ladder, and any Claude web call adds its cost to the copyright bucket.

**Goal:** turn copyright resolution into the signed precedence chain — file
extraction → npm registry `author` → Claude web inference → `UNKNOWN` — without
overwriting an earlier success, capturing the Claude web call's cost into the
existing `copyright_meta` (Inference Cost).

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked**.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P2's Status is `done` in `PLAN.md`'s phase table
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥98 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

- **Signed precedence** (`DECISIONS.md` "Copyright fallback chain"), never
  overwriting an earlier success: 1. verbatim from LICENSE via GPT-4.1 (already
  in `copyright.extract_copyright`). 2. npm purls only — registry metadata,
  accept ONLY `author.name` or the string form of `author`; strip email/URL;
  emit `Copyright (c) {name}`; NOT `contributors`/`maintainers`. 3. Claude web
  research for a source-backed verbatim statement. 4. all fail → keep `UNKNOWN`.
- **Claude web return** (`DECISIONS.md`): JSON `{"copyright": "<verbatim or
  UNKNOWN>", "reasoning": "..."}`; existing Claude retry policy; preserves
  raw/cost/token metadata; rejects placeholders + unsupported guesses; counts
  toward Inference Cost (→ `copyright_meta`).
- After P2: `copyright.extract_copyright(license_text) -> (dict, CallMeta)`
  (confirm from P2 Outcome). `_is_placeholder_copyright(text)` and
  `_unknown(reason)` exist and are reusable for the web result.
- After P1: `claude_client.infer_license(...) -> (dict, CallMeta)` with helpers
  `_claude_once`, `_parse_cli_stdout`, `with_retries`, `_classify`, `_unknown` —
  mirror them for a web copyright call.
- `src/prompts.py` holds `license_prompt`+`LICENSE_SCHEMA` and `copyright_prompt`.
  Add a Claude web-copyright prompt + schema (like `LICENSE_SCHEMA`, keys
  `copyright`, `reasoning`). Old wording: `knowledge/old_code/src/config.py` +
  `copyright_extractor.infer_copyright`.
- **npm purl → name:** parse `pkg:npm/{name}@{ver}` (URL-decode; `%40`→`@`).
  `download.py::npm_candidates` shows the parse; replicate name-only extraction
  locally (small duplication is fine — do not edit `download.py`). Registry:
  `https://registry.npmjs.org/{name}`; `author` is a string `"Name <email>
  (url)"` or an object with `name`.
- `pipeline.process_component` (post-P2) does `cr, cr_meta = await
  extract_copyright(text)` (~line 117) only when a file exists; has `comp.purl`,
  `comp.lib_name`, `comp.version`, `model` in scope. Cache hits skip this.

## Files

**Touch (complete list):**

- `src/prompts.py` — edit: add Claude web-copyright prompt + JSON schema.
- `src/claude_client.py` — edit: add `infer_copyright_web(purl, lib_name,
  version, model) -> (dict, CallMeta)` reusing the retry/parse/meta machinery.
- `src/copyright.py` — edit: add npm-author fetch + a `resolve_copyright(
  license_text, purl, lib_name, version, model) -> (dict, CallMeta)` chaining
  the three sources; keep `extract_copyright` as the file step.
- `src/pipeline.py` — edit: call `resolve_copyright(...)` and fold its meta into
  `copyright_meta`; log one `copyright:` story line describing the ladder.
- `tests/test_copyright.py` — edit: npm-author parse + strip; chain order &
  no-overwrite; placeholder rejection on web result.
- `tests/test_claude_client.py` — edit: `infer_copyright_web` success/UNKNOWN.

**Do not touch:** `src/download.py` (replicate the tiny purl parse locally),
`src/summary.py` (P4), `src/gpt41_client.py`, `src/pricing.py`/`src/equality.py`
(reuse only), and anything not listed.

## Tasks

### T1: Claude web copyright call

- Steps: in `src/prompts.py` add `copyright_web_prompt(purl, lib_name, version)
  -> (str, dict)` returning a web-research prompt and a schema with required
  `copyright`, `reasoning` (mirror `LICENSE_SCHEMA` structure). In
  `src/claude_client.py` add `infer_copyright_web(...)` that runs the same
  `_claude_once` + `with_retries` + `CallMeta` capture as `infer_license`, parses
  `{copyright, reasoning}`, and fails closed to `{"copyright":"UNKNOWN", ...}` on
  hard/exhausted/parse errors — always returning the accumulated `CallMeta`.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_claude_client.py -q`
  → exit 0 (mocked CLI: valid `{copyright, reasoning}` → returned + meta cost;
  hard failure → UNKNOWN + meta with 0 billable calls).
- Commit when green.

### T2: npm author fallback + chain orchestrator

- Steps: in `src/copyright.py` add `_npm_author_copyright(purl) -> str | None`
  (return `Copyright (c) {name}` from registry `author.name`/string form, email
  and URL stripped; `None` for non-npm, network failure, missing/blank author,
  or placeholder). Add `resolve_copyright(license_text, purl, lib_name, version,
  model)`: run `extract_copyright` (file); if UNKNOWN and npm, try
  `_npm_author_copyright`; if still UNKNOWN, try `infer_copyright_web` (reject
  placeholders/UNKNOWN); return the first success plus a merged `CallMeta` (file
  + web; npm contributes none). Never overwrite a found value.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -q` →
  exit 0 (file success → no fallback called; file UNKNOWN + npm author → npm
  value, web NOT called; both file+npm UNKNOWN → web value; author string with
  email/url → stripped `Copyright (c) Name`; contributors/maintainers ignored).
- Commit when green.

### T3: wire the chain into the pipeline

- Steps: in `process_component`, replace the file-only `extract_copyright` call
  with `resolve_copyright(text, comp.purl, comp.lib_name, comp.version, model)`;
  store `copyright_meta` from the merged meta; keep the single `copyright:`
  story line (its reasoning now names which source won). When no license file
  exists, still attempt npm/web per precedence (call `resolve_copyright` with
  empty license text) — item 1 short-circuits to UNKNOWN on empty text, then
  2/3 run.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q` →
  exit 0. Then full suite (Validation gate).
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥101 passed.
2. No separate lint/typecheck gate in this repo.
3. Fresh review: `git diff {baseline from PLAN.md}..HEAD` reviewed against this
   doc plus an over-engineering lens by a context that did not implement it
   (subagent given only the diff, this doc, and the lens; if unavailable, stop
   and ask the user). Fix findings, re-run 1. A lens finding on the small purl
   parse duplication is NOT fixed (this doc ordered it); record it as a note.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥101 passed.
- A test proves precedence: file UNKNOWN + mocked npm `author` yields `Copyright
  (c) {name}` with the web call never made; file+npm UNKNOWN + a mocked web
  result yields that result with its cost in the returned `CallMeta`.

## Rollback

To abandon this phase: `git reset --hard {baseline hash from PLAN.md's phase
table}`, then set this phase's Status to `blocked` in `PLAN.md` with a one-line
reason in your Phase-notes block.

## Failure modes

1. Registry `author` absent or only `contributors`/`maintainers` → npm step
   returns `None` (do NOT use those fields); chain proceeds to web.
2. Web returns a plausible-but-unsupported guess → rejected by
   `_is_placeholder_copyright` + the UNKNOWN check; keep `UNKNOWN`.
3. Registry network flakiness → treat as `None` (fail soft), never crash; the
   web step still runs.

## Anti-goals

Do not, even if it seems better:

- No `contributors`/`maintainers` fallback — `author` only, per DECISIONS.
- No broadening deterministic download to non-npm ecosystems (BACKLOG #2).
- No touching `src/summary.py` (P4) or `src/download.py`.
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here"
  fixes. Spare capacity goes into verification, not scope.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list, do not edit another
phase's doc.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set Status `done`, fill Baseline + Updated.
3. In `PLAN.md`, reflect a concise outcome — confirm `resolve_copyright`'s
   signature and that `copyright_meta` may now carry multiple billable calls.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: file → npm author → Claude web copyright chain with cost capture
HEAD: {git rev-parse --short HEAD} | Branch: {git branch --show-current}
Files changed: {git diff --name-only <baseline>..HEAD output}
Commands run: {the Verify/gate commands and their observed results}
Test status: {suite command + observed result}
Assumptions: {numbered, or "none"}
Open questions: {numbered, or "none"}
Next action: P4 per PLAN.md's table
```
