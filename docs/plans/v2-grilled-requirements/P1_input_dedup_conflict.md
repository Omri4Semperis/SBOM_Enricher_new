# P1: input_dedup_conflict

**Plan:** v2 grilled requirements — deliver the five 2026-07-19 signed-off
requirements for the SBOM Enricher. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** Write freely here during implementation. Your only other
editable file is `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other phases' blocks); never another phase's `P*` doc.

**Demo:** an input CSV that repeats a `component_name` (same identity) parses
to a single component; the same name with a differing `purl` or ground-truth
value aborts the run naming the component and the field.

**Goal:** Implement requirement A / ADR 0011 in `src/input_csv.py`. Stop
rejecting on duplicate `component_name`; reject only on a *conflict*. Keep the
first occurrence's literal values for the deduped output. Additionally
aggregate, per unique component, the ordered set of raw `project_name` values
across its rows (new `Component.project_names`) so P3 can lay out license files
by project.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] No dependencies (this phase has none)
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, 157 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

`src/input_csv.py` today (read it first):

- `Component` is `@dataclass(frozen=True)` with fields `component_name, purl,
  lib_name, version, slug, extras: dict[str,str]`. `extras` holds every
  non-`component_name`/`purl` column (passthrough + any GT columns).
- `read_components(path)`:
  1. opens with `encoding="utf-8-sig"`, `csv.DictReader`;
  2. requires `component_name` and `purl` columns;
  3. `passthrough = [c for c in fields if c not in ("component_name","purl")]`;
  4. loops rows: strips `component_name`, raises `SystemExit` on empty, and
     **raises `SystemExit(f"duplicate component_name: {name!r}")` on any repeat**
     (this is the reject-any-duplicate behavior to replace);
  5. builds a slug→names map and raises `SystemExit` on slug collision
     (**keep this — F3**);
  6. builds one `Component` per row.

Requirement A (from ADR 0011; detail in
`docs/archive/DECISIONS_2026-07-19_grilled-requirements.md` §A):

- A1/A2: conflict = same `component_name` with a differing `purl` OR any
  differing **present** GT field (`license_name`, `license_code_url`,
  `copyright`). Passthrough columns (e.g. `project_name`) may differ freely and
  are NOT conflicts.
- A3: conflict comparison normalizes aggressively: trim, collapse internal
  whitespace to single spaces, casefold. So `""` vs `"MIT"` IS a conflict
  (empty-vs-populated), but `"MIT"` vs `" mit "` is NOT.
- A4: non-conflicting duplicates → the **first occurrence's literal** values
  win in the deduped `Component` (its `extras`, `purl`, etc. are the first
  row's raw strings, unnormalized).
- A5: enrichment runs once per unique component (guaranteed by returning one
  `Component` per name).
- A6: a conflict fails the whole run immediately via `SystemExit`, naming the
  component and the differing field. No outputs produced (raising before the
  run dir is created satisfies this; `read_components` is called before
  `create_run_dir` in `main.run`).

The three GT field names live as `GT_COLUMNS` in `src/results_csv.py`
(`("license_name","license_code_url","copyright")`); either import that tuple
or hardcode it locally — hardcoding is acceptable and dependency-free.

`Component.project_names` (new, for P3): the ordered, first-seen-unique raw
`project_name` values across all rows of a component. **Empty tuple when the
input has no `project_name` column.** When the column exists, include the raw
value of each row (a blank value contributes `""` to the set — P3 maps `""` to
`_misc`). "Raw" = the cell value as read (not stripped/normalized) so P3 can
sanitize it itself; if in doubt keep it verbatim.

Gotcha: `read_components` return type stays `list[Component]`; callers
(`main.run`, `create_run_dir`, `run_workers`) already treat it as a list and
read `.extras` / `.component_name` — adding a field and deduping does not break
them. Do not change the return type.

## Files

**Touch (complete list):**

- `src/input_csv.py` — edit: add `project_names` to `Component`; rewrite the
  row loop to dedup + conflict-check + aggregate projects.
- `tests/test_input_csv.py` — edit: add tests for allow-duplicate,
  conflict-rejection (purl and each GT field), normalization edges, first-win
  literals, and `project_names` aggregation (incl. absent-column empty tuple).

**Do not touch:** `src/results_csv.py` (import `GT_COLUMNS` or hardcode; don't
edit it), `src/pipeline.py`, `src/main.py`, and anything not listed under
Touch. Needing an unlisted file means the plan is wrong: record it as a note
in this doc and a comment in your `PLAN.md` block; if the phase can't proceed
without it, follow **If blocked**.

## Tasks

### T1: dedup + conflict rejection + project_names

- Steps:
  - Add `project_names: tuple[str, ...] = field(default_factory=tuple)` to
    `Component` (import `field` is already present).
  - Write a module-level normalizer, e.g.
    `def _norm(v: str) -> str: return " ".join((v or "").split()).casefold()`.
  - Determine `has_project = "project_name" in fields` after reading
    `fieldnames`.
  - Replace the reject-any-duplicate loop with a first-seen accumulation keyed
    by stripped `component_name`, preserving input order:
    - First time a name is seen: store the row as its canonical row and start
      an ordered project list (append the row's raw `project_name` if
      `has_project`).
    - Repeat name: compare against the canonical row. Conflict if
      `_norm(purl)` differs, or for each GT field present in `fields`,
      `_norm(row[gt])` differs. On conflict raise
      `SystemExit(f"conflict for component {name!r}: {field} differs "
      f"({canonical_value!r} vs {row_value!r})")` — name the component and the
      first differing field. Otherwise append this row's raw `project_name` to
      the component's project list if not already present (first-seen unique).
  - Keep the existing slug-collision check (F3), but run it over the **unique**
    component names.
  - Build one `Component` per unique name from its canonical (first) row, with
    `project_names=tuple(project_list)` (empty tuple when `not has_project`).
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_input_csv.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: tests for A + project_names

- Steps: add to `tests/test_input_csv.py` (use `tmp_path` to write CSVs):
  - duplicate identical rows → one `Component`; `project_names` empty when no
    `project_name` column.
  - duplicate with differing `purl` → `SystemExit` mentioning the name.
  - duplicate with differing each present GT field → `SystemExit`; and
    empty-vs-populated GT counts as a conflict (A3).
  - duplicate with only differing passthrough (incl. `project_name`) → NO
    error; one `Component`; first row's literals win (A4).
  - `project_name` column present across N rows → `project_names` is the
    ordered first-seen-unique set (blank cell contributes `""`).
  - `"MIT"` vs `" mit "` on a GT field → NOT a conflict (normalization).
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_input_csv.py -q`
  → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥157 passed (baseline
   157 plus the tests you added; none removed).
2. No separate typecheck/lint in this repo — step 1 covers it.
3. Fresh review: the diff `git diff {baseline}..HEAD` (baseline = the hash you
   recorded in `PLAN.md` at phase start) is reviewed against this doc plus an
   over-engineering lens by a context that did not implement it (subagent given
   only the diff, this doc, and the lens; if subagents are unavailable, stop
   and ask the user to review in a new session). Fix findings, re-run 1 — but a
   lens finding on something this doc explicitly ordered (e.g. carrying
   `project_names` for P3) is NOT fixed; record it as a note here and, if it
   affects another phase, an Incoming comment in that phase's `PLAN.md` block.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_input_csv.py -q` → exit 0,
  all passed (including the new duplicate-allowed and conflict-reject tests).
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥157 passed.

## Anti-goals

Do not, even if it seems better:

- No project-directory sanitizing/collision logic here — P3 owns turning
  `project_names` into paths. This phase only *collects* the raw names.
- No enriched-CSV or raw-row reader here — P2 owns `read_input_rows`.
- No change to `read_components`'s return type or to callers.
- No removal of the slug-collision reject (F3 keeps it).

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
   — confirm the `Component.project_names` contract for P2/P3. Keep it short;
   write the full detail below and point to it.
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
