# P3: license_file_layout

**Plan:** v2 grilled requirements — deliver the five 2026-07-19 signed-off
requirements for the SBOM Enricher. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** Write freely here during implementation. Your only other
editable file is `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other phases' blocks); never another phase's `P*` doc.

> Sizing note: long because requirement C is one cohesive capability touching
> four source files — an allowed single phase per SKILL.md Sizing.

**Demo:** on an input with a `project_name` column, a component's downloaded
license file appears at `licenses/{project}/{slug}.ext` for every project it
belongs to (blank project → `licenses/_misc/...`); with no such column it stays
flat at `licenses/{slug}.ext`; a cache hit restores to the same places.

**Goal:** Implement requirement C (and F2/F3-adjacent layout) from
`docs/adr/0014` and §C/§F of
`docs/archive/DECISIONS_2026-07-19_grilled-requirements.md`. Route downloaded
license files into per-project
subdirectories driven by `Component.project_names` (from P1), keep
`per_component/{slug}/` flat, and make cache restore obey the same layout.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc (esp. the flat-default note for P4)
- [ ] P1 Status is `done` in `PLAN.md`'s phase table (needs `Component.project_names`)
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥157 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

Requirement C (from ADR 0014; detail in
`docs/archive/DECISIONS_2026-07-19_grilled-requirements.md` §C/§F):

- C1: one project per input row; a component in N projects = N rows; its
  license file is written under EACH of its projects' directories.
- C2: `project_name` present → files live ONLY under
  `licenses/{project}/{slug}.ext` (no flat top-level copy). `project_name`
  absent (no such column) → current flat `licenses/{slug}.ext`.
- C3: blank `project_name` (column exists, cell empty) → `licenses/_misc/{slug}.ext`.
- C4: the project split touches ONLY `licenses/`. `per_component/{slug}/` stays
  flat, one dir per unique component.
- C5: sanitize project names with the existing slug sanitizer (`make_slug` in
  `input_csv.py`); distinct RAW names colliding to the same dir → first-seen
  keeps the base name, later ones get `(1)`, `(2)`, … suffixes.
- F2: cache stays keyed by `component_name`; on a hit, restore obeys THIS run's
  layout (per-project dirs / `_misc` / flat).

Inputs from P1: `Component.project_names: tuple[str, ...]` — ordered,
first-seen-unique RAW project values across the component's rows; empty tuple
when the input has no `project_name` column. A blank cell contributes `""`.

Current code to change:

- `src/download.py`
  - `_write_license(dest_dir, slug, ext, body) -> Path` writes
    `licenses/{slug}{ext}` AND `per_component/{slug}/{name}`, returns the flat
    licenses path.
  - `fetch_license_file(claude_url, purl, dest_dir, slug) -> DownloadResult`
    calls `_try_one` per candidate; `_try_one` calls `_write_license` and sets
    `saved_path`.
- `src/cache.py` — `restore_license_file(record, run_dir, slug) -> Path` mirrors
  `_write_license`'s flat layout on a cache hit.
- `src/pipeline.py` — `process_component(comp, run_dir, model, client, *,
  cache_read, cache_write)`; calls `restore_license_file(cached, run_dir,
  comp.slug)` on hit and `fetch_license_file(url, comp.purl, run_dir,
  comp.slug)` on miss. `run_workers(config, components, run_dir, writer,
  gt_columns)` owns the `components` list.
- `src/run_dir.py` — has `make_slug` available via `input_csv`; good home for a
  run-wide project-dir map builder.

Design (laziest correct):

- New `build_project_dir_map(components) -> dict[str, str]` in `run_dir.py`:
  iterate components in order, then each component's `project_names` in order;
  map each RAW name to a directory name. Rule: `""` → `"_misc"`; else
  `make_slug(raw.strip())`. Track used dir names; on a collision from a
  *different* raw name, append `(1)`, `(2)`, … to the base until unique
  (first-seen raw keeps the base). Same raw name always maps to the same dir.
  Returns `{}` when no component has any project_names (flat mode overall).
- `_write_license` gains a `project_dirs: list[str] | None = None` param
  (KEEP the `None` → flat branch — P4 depends on it). When `project_dirs` is a
  non-empty list, write `licenses/{pdir}/{slug}{ext}` for each pdir (dedup the
  list first); always write the single flat `per_component/{slug}/{name}` copy
  (C4). Return a canonical path = the first project copy written (or the flat
  path when `project_dirs` is None/empty). Reading bytes for copyright/cache
  from any copy is equivalent.
- `fetch_license_file` gains `project_dirs: list[str] | None = None`, threaded
  through `_try_one` to `_write_license`.
- `restore_license_file` gains `project_dirs: list[str] | None = None`,
  mirroring `_write_license`'s layout (flat when None/empty).
- `process_component` gains `project_map: dict[str, str] | None = None`.
  Compute this component's dir list once:
  `dirs = [project_map[r] for r in comp.project_names]` (only when
  `project_map` and `comp.project_names`; dedup preserving order) else `None`.
  Pass `dirs` to BOTH `restore_license_file` (cache hit) and
  `fetch_license_file` (miss).
- `run_workers` builds the map once (`build_project_dir_map(components)`) and
  passes it into every `process_component` call.

Gotchas:
- Dedup `project_dirs` before writing so a component listed twice under the
  same project doesn't double-write; create subdirs with `mkdir(parents=True,
  exist_ok=True)` (the pre-created empty `run_dir/licenses` is fine).
- Do not change `ComponentResult.license_file_path`'s meaning: it stays a
  single canonical path (first copy). Copyright extraction and cache write read
  from it — both must keep working.

## Files

**Touch (complete list):**

- `src/run_dir.py` — edit: add `build_project_dir_map(components)`.
- `src/download.py` — edit: `_write_license` + `_try_one` + `fetch_license_file`
  gain `project_dirs`; per-project writes; flat default preserved.
- `src/cache.py` — edit: `restore_license_file` gains `project_dirs`.
- `src/pipeline.py` — edit: `process_component` gains `project_map`, computes
  per-component dirs, passes to restore/fetch; `run_workers` builds + passes map.
- `tests/test_run_dir.py` — edit: map builder (blank→_misc, absent→empty,
  collision suffixes, stable per raw name).
- `tests/test_download.py` — edit: per-project writes, flat default, dedup.
- `tests/test_cache.py` — edit: restore per-project + flat.

**Do not touch:** `src/equality.py` (P4 owns it), `src/main.py` (map is built
in `run_workers`, not `main`), and anything not listed under Touch. Needing an
unlisted file means the plan is wrong: note it here + a comment in your
`PLAN.md` block; if blocked, follow **If blocked**.

## Tasks

### T1: project-dir map builder

- Steps: add `build_project_dir_map(components)` to `src/run_dir.py` per the
  Design (import `make_slug` from `input_csv`). Add tests to
  `tests/test_run_dir.py`: no project_names → `{}`; blank → `_misc`; two
  distinct raw names sanitizing to the same slug → base + `(1)`; same raw name
  across components → one stable dir.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_run_dir.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: project-aware download writes

- Steps: thread `project_dirs` through `_write_license`, `_try_one`,
  `fetch_license_file` in `src/download.py`. Non-empty list → write one copy per
  (deduped) project dir under `licenses/{pdir}/`; empty/None → flat as today;
  always one flat `per_component/{slug}/` copy; return first copy path. Add
  tests to `tests/test_download.py`: flat default unchanged; a two-project list
  writes both `licenses/a/{slug}.ext` and `licenses/b/{slug}.ext` and one
  per_component copy; duplicate dirs in the list write once.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T3: cache restore + pipeline wiring

- Steps:
  - `src/cache.py`: `restore_license_file(record, run_dir, slug,
    project_dirs=None)` mirrors T2's layout (flat when None/empty). Add tests
    to `tests/test_cache.py` (flat still works; per-project restore writes
    under each dir + one per_component copy).
  - `src/pipeline.py`: `process_component(..., project_map=None)`; compute
    `dirs` once from `project_map` + `comp.project_names` (dedup, preserve
    order; `None` when either is empty); pass to `restore_license_file` and
    `fetch_license_file`. In `run_workers`, build the map via
    `build_project_dir_map(components)` and pass `project_map=` in the
    `process_component(...)` call.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_cache.py tests/test_pipeline.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T4: full suite

- Steps: run the whole suite; fix any fallout from the signature changes
  (existing callers that pass positionally). All new params are keyword/optional
  with flat defaults, so existing tests should pass unchanged.
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
   ordered (writing one copy per project; keeping the flat default for P4) is
   NOT fixed; record it as a note here and, if it affects another phase, an
   Incoming comment in that phase's `PLAN.md` block.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_download.py tests/test_cache.py tests/test_run_dir.py -q`
  → exit 0, all passed (per-project + flat + `_misc` + collision).
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.

## Anti-goals

Do not, even if it seems better:

- Do NOT remove or change the flat (`project_dirs=None`) branch — P4's GT
  download relies on it (see PLAN.md P3 Incoming comment).
- No per-project split of `per_component/` — it stays flat (C4).
- No change to the cache KEY or write side — cache stays `component_name`-keyed
  (F2); only restore layout changes.
- No building the map in `main.py` — build it in `run_workers`.
- No new dependency; use stdlib + existing `make_slug`.

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
   (confirm the flat default survived, for P4). Keep it short; write full detail
   below.
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
