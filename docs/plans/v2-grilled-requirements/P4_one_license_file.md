# P4: one_license_file

**Plan:** v2 grilled requirements — deliver the five 2026-07-19 signed-off
requirements for the SBOM Enricher. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** Write freely here during implementation. Your only other
editable file is `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other phases' blocks); never another phase's `P*` doc.

**Demo:** an audit run with a ground-truth `license_code_url` no longer creates
a second `{slug}__eq_inf` copy; after the run, `licenses/` holds only the
inferred license file per component (no `__eq_gt` leftovers).

**Goal:** Implement requirement D / ADR 0013. Audit URL equality still compares
LICENSE *content*, but the inferred side REUSES the file already saved during
enrichment (never re-downloaded). The ground-truth file is still fetched for
the comparison, then removed from `licenses/` so that tree contains only the
inferred file. `per_component/{slug}/` may keep both copies.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] No dependencies (independent of P3; works against flat or per-project `licenses/`)
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥157 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

Requirement D (from ADR 0013; detail in
`docs/archive/DECISIONS_2026-07-19_grilled-requirements.md` §D):

- D1: never re-download the inferred URL; reuse the enrichment-saved file for
  the audit comparison (no `__eq_inf` file).
- D2: still download the GT file to compare contents, but remove it from
  `licenses/` afterward → `licenses/` holds only the inferred file per
  component.
- D3: `per_component/{slug}/` may keep everything (inferred + GT copies).
- D-edge (accepted): if enrichment downloaded no inferred file but an inferred
  URL exists, the inferred side has nothing to reuse → equality stays FALSE.

Current code (read first):

`src/equality.py` — `compare_url_content(inferred_url, gt_url, dest_dir, slug,
*, client=None)`:

- downloads BOTH via `fetch_license_file(url, "", dest_dir, f"{slug}__eq_inf")`
  and `...f"{slug}__eq_gt"`, each writing into `licenses/` + `per_component/`;
- inferred download fail → `EqResult("FALSE", "inferred_url_download_failed")`;
- GT fail → `UNSCOREABLE` when `fail_kind == "html"` (`gt_not_a_file`), else
  `FALSE`;
- compares bytes: identical → TRUE; normalized-equal → TRUE; else GPT judge
  (or FALSE when `client is None`).

`src/pipeline.py` — `apply_equality(...)` calls, for the URL branch:
`compare_url_content(result.inferred_license_code_url,
extras.get("license_code_url",""), run_dir, slug, client=client)`.
`result.license_file_path: Path | None` is the enrichment-saved inferred file
(set on both the download path and the cache-hit path). This is the file to
reuse.

Design (laziest correct):

- Change the signature to take the already-saved inferred file, not a URL:
  `compare_url_content(inferred_path: Path | None, gt_url, dest_dir, slug, *,
  client=None)`.
  - If `inferred_path is None` or not a file → return
    `EqResult("FALSE", "inferred_file_missing")` (D-edge). Do NOT download GT in
    this case (nothing to compare against; also avoids a stray GT file).
  - Else read `inferred_path.read_bytes()` for the inferred side.
- GT: keep using `fetch_license_file((gt_url or "").strip(), "", dest_dir,
  f"{slug}__eq_gt")` with NO project context, so it writes the flat
  `licenses/{slug}__eq_gt.ext` (relies on P3 keeping the flat default; works
  today too). Same GT fail handling as now (`gt_not_a_file` → UNSCOREABLE).
- After reading the GT bytes for comparison, DELETE the flat `licenses/` GT
  copy (`gt.saved_path.unlink(missing_ok=True)`) — D2. Do this before returning
  any verdict once GT was fetched (success or judge path). The `per_component/`
  GT copy stays (D3); do not touch it.
- The comparison ladder (identical / normalized / judge) is unchanged; it just
  operates on `inferred_bytes` and the GT bytes read before deletion.
- `apply_equality`: pass `result.license_file_path` (not the URL) as the first
  argument.

Gotchas:

- Read the GT bytes into memory BEFORE unlinking, then compare.
- `unlink(missing_ok=True)` guards the (rare) case the flat copy isn't where
  expected; never raise from cleanup.
- Do not delete the inferred file — it is the deliverable and is also read by
  copyright/cache. You only ever reuse (read) it here.
- No change to the `UNSCOREABLE`/`gt_not_a_file` semantics (ADR 0006).

## Files

**Touch (complete list):**

- `src/equality.py` — edit: `compare_url_content` signature + reuse inferred
  file + GT-copy deletion.
- `src/pipeline.py` — edit: `apply_equality` passes `result.license_file_path`
  to `compare_url_content`.
- `tests/test_equality.py` — edit: reuse-inferred-file, GT-deletion,
  missing-inferred → FALSE, `gt_not_a_file` → UNSCOREABLE still holds.
- `tests/test_pipeline.py` — edit: `apply_equality` URL branch passes the path.

**Do not touch:** `src/download.py` (reuse `fetch_license_file` as-is for GT;
do not add an inferred-download-skip flag there), `src/cache.py`, and anything
not listed under Touch. Needing an unlisted file means the plan is wrong: note
it here + a comment in your `PLAN.md` block; if blocked, follow **If blocked**.

## Tasks

### T1: reuse inferred file + delete GT copy

- Steps: rewrite `compare_url_content` in `src/equality.py` per the Design:
  new first param `inferred_path: Path | None`; missing → `FALSE
  inferred_file_missing` (no GT fetch); else read inferred bytes, fetch GT
  (flat), handle GT failure as today, read GT bytes, `unlink(missing_ok=True)`
  the flat GT copy, then run the existing identical/normalized/judge ladder.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_equality.py -q`
  → exit 0, all passed (update the URL-content tests to pass a written temp
  file path as the inferred side; assert the flat GT copy is gone afterward).
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: pipeline wiring + tests

- Steps: in `src/pipeline.py` `apply_equality`, change the URL branch to
  `compare_url_content(result.license_file_path, extras.get("license_code_url",
  ""), run_dir, slug, client=client)`. Update `tests/test_pipeline.py` so the
  URL-equality path exercises a `license_file_path` (a component with a saved
  inferred file yields a real comparison; one with `license_file_path=None`
  yields `is_eq_license_code_url == "FALSE"`).
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T3: full suite

- Steps: run the whole suite; fix any other callers of `compare_url_content`
  surfaced by the signature change (search the tree first).
- Verify: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
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
   ordered (reusing the inferred file; deleting only the flat GT copy) is NOT
   fixed; record it as a note here and, if it affects another phase, an Incoming
   comment in that phase's `PLAN.md` block.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_equality.py -q` → exit 0,
  all passed (reuse-inferred, GT-deletion, missing-inferred FALSE, UNSCOREABLE).
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.

## Anti-goals

Do not, even if it seems better:

- No re-download of the inferred URL, and no `__eq_inf` file (D1).
- Do not delete or move the `per_component/` GT copy (D3), nor the inferred
  deliverable file.
- No change to `UNSCOREABLE`/`gt_not_a_file` grading (ADR 0006).
- No new "skip write" flag inside `download.py` — reuse `fetch_license_file`
  for GT and just delete the flat copy afterward.

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
