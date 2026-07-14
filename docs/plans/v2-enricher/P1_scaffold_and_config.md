# P1: scaffold_and_config

**Your workspace.** This doc is writable: during implementation, record
whatever detail you need here (decisions, dead ends, findings). The other
file you may edit is `PLAN.md` — your row in the phase table, a concise
reflection in your own Phase-notes block, and **Incoming comments** in
*another* phase's block when you discover something it must know. You never
edit another phase's `P*` doc. Status is tracked in `PLAN.md`'s table, not here.

**Demo:** `.\.venv\Scripts\python.exe -m pytest -q` passes, and loading a
config with a bogus `model` exits fast with a one-line message.

**Goal:** Stand up the test harness and the config loader. `load_config` reads
`configs/default.json`, validates it against the locked rules, and returns a
frozen `Config` object other phases build on. Nothing runs the pipeline yet.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [x] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [x] `git status --porcelain` → empty (clean tree)
- [x] `.\.venv\Scripts\python.exe -c "import openai, azure.identity; print('ok')"` → prints `ok`

## Deviations

1. **T1 Verify exit code:** with 0 tests collected, `pytest -q` exits **5** (not 0).
   Doc said "exit 0 (0 tests collected is fine)". Treated exit 5 as the
   expected no-tests success for T1 only; T3/gate require real tests → exit 0.
2. **pytest install:** `pip install pytest` into `.venv` only (pytest 9.1.1);
   not added to `requirements.txt` (repo has none for dev deps), as directed.

## Validation review notes

Fresh review ([P1 diff review](f0aeb5b3-df5a-450f-ac4f-74e10d9d768f)): **PASS**, no must-fix findings.
Doc-ordered / record-only lens notes (not fixed):
- `conftest.py` sys.path insert — required by T1
- full `MODEL_CHOICES` seed — required
- private helpers under `load_config` — fine, not schemas/env layers
- `__future__ annotations` cosmetic on 3.13 — unused for `|` syntax

## Context capsule

- Repo is greenfield for source: `src/` and `tests/` exist but are **empty**.
  Run style (locked): `python src/main.py` auto-loads `configs/default.json`.
- `.venv` already has runtime deps; it does **not** have `pytest`. Install it
  into the venv (do not add it to `requirements.txt` unless the repo already
  tracks dev deps — it does not, so a plain `pip install pytest` into `.venv`
  is enough; note it in this doc).
- `configs/default.json` (exact current content — the schema to honor):

```json
{
  "input_file_path": "input/GT_dedup_with_purl1.csv",
  "output_base_path": "runs",
  "run_name": null,
  "model": "claude-opus-4-8",
  "workers": 20,
  "cache_read": null,
  "cache_write": "caches"
}
```

- Locked validation rules (DECISIONS "default.json field set"):
  - `input_file_path` — required string. Loader resolves it relative to repo
    root but does **not** check the file exists (P2 owns input validation).
  - `output_base_path` — required string.
  - `run_name` — optional; `null`/empty → `None`.
  - `model` — must be in a fixed allow-list `MODEL_CHOICES`. Seed it with
    `"claude-opus-4-8"` (the default) plus the other Claude ids from old
    `knowledge/old_code/src/config.py` `MODEL_CHOICES` if present; a typo must
    fail fast. GPT-4.1 is NOT a config field.
  - `workers` — int in `[1, 30]` inclusive.
  - `cache_read` / `cache_write` — nullable path strings; `null`/empty →
    `None` (skip cache silently later).
- Keep on-disk key names exactly as-is (no renaming). Fail-fast = raise
  `SystemExit(message)` with one concise line; no stack-dump to the user.
- Old `run_config.py` / `paths.py` show one way to do this — heavier than we
  need. A single dataclass + one loader function is enough.

## Files

**Touch (complete list):**

- `src/config.py` — create: `Config` frozen dataclass, `MODEL_CHOICES`,
  `load_config(path: Path | str) -> Config`.
- `tests/test_config.py` — create: tests for the loader (happy path + each
  fail-fast rule).
- `tests/conftest.py` — create: add repo `src/` to `sys.path` so `import
  config` works when running `pytest` from repo root. (Simplest path; no
  packaging.)

**Do not touch:** `configs/default.json` (read only), anything under
`knowledge/`, and any file not listed above.

## Tasks

### T1: pytest harness

- Steps: `.\.venv\Scripts\python.exe -m pip install pytest`. Create
  `tests/conftest.py` inserting `src/` onto `sys.path`
  (`sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))`).
- Verify: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0 (0 tests collected
  is fine at this point).
- Commit when green.

### T2: Config loader

- Steps: create `src/config.py` with the frozen `Config` dataclass, the
  `MODEL_CHOICES` tuple, and `load_config`. Parse JSON, apply every locked
  rule, resolve paths relative to repo root, coerce null/empty nullable fields
  to `None`, raise `SystemExit("<one line>")` on any violation.
- Verify: `.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); import config; print(config.load_config('configs/default.json').model)"`
  → prints `claude-opus-4-8`.
- Commit when green.

### T3: Loader tests

- Steps: create `tests/test_config.py`: happy-path load of `default.json`;
  unknown `model` → `SystemExit`; `workers=0` and `workers=31` → `SystemExit`;
  `run_name=null` → `None`; `cache_read=""` → `None`. Write configs as temp
  files (`tmp_path`).
- Verify: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. Fresh review: `git diff {baseline}..HEAD` reviewed against this doc plus an
   over-engineering lens by a context that did not implement it (Cursor Task
   tool → `generalPurpose` subagent, readonly, given only the diff, this doc,
   and the lens). Fix findings, re-run 1. A lens finding on something this doc
   explicitly ordered is NOT fixed; record it here and, if it affects another
   phase, an Incoming comment in that phase's `PLAN.md` block.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- `.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); import config; config.load_config('configs/default.json')"`
  → exit 0 (no output needed).

## Rollback

To abandon this phase: `git reset --hard {baseline hash from PLAN.md's phase
table}`, then set this phase's Status to `blocked` in `PLAN.md` with a one-line
reason in your Phase-notes block.

## Failure modes

1. `pytest` can't import `config` → `conftest.py` sys.path insert is missing or
   wrong; confirm it runs before collection and points at `src/`.
2. Over-building the loader (validators, schemas library, env overrides) →
   stop; the rules are a handful of `if` checks. One dataclass, one function.

## Anti-goals

Do not, even if it seems better:

- No CLI arg parsing / no `argparse` (old `cli.py`) — config is file-only for
  now; a later phase adds args only if a decision requires it.
- No config for GPT-4.1 model — it is fixed in source (P5 owns it).
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here"
  fixes. Spare capacity goes into verification.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (the start
   hash) and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block
   — confirm the final `Config` field names/types and `MODEL_CHOICES` contents
   so P2+ rely on the real shape. Keep it short; full detail below.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: test harness + validated config loader
HEAD: {git rev-parse --short HEAD} | Branch: {git branch --show-current}
Files changed: {git diff --name-only <baseline>..HEAD output}
Commands run: {the Verify/gate commands and their observed results}
Test status: {suite command + observed result}
Assumptions: {numbered, or "none"}
Open questions: {numbered, or "none"}
Next action: P2 (input_run_dir_stub)
```

## Outcome

Objective: test harness + validated config loader
HEAD: PENDING | Branch: master
Files changed:
- docs/plans/v2-enricher/P1_scaffold_and_config.md
- docs/plans/v2-enricher/PLAN.md
- src/config.py
- tests/conftest.py
- tests/test_config.py
Commands run:
- `pip install pytest` → pytest 9.1.1 installed in `.venv`
- `pytest -q` (T1, 0 tests) → exit 5 (deviation; accepted)
- `python -c "... load_config(...).model"` → `claude-opus-4-8`
- `pytest -q` (T3/gate/exit) → 6 passed, exit 0
- `python -c "... load_config('configs/default.json')"` → exit 0
Test status: `.\.venv\Scripts\python.exe -m pytest -q` → 6 passed
Assumptions: none
Open questions: none
Next action: P2 (input_run_dir_stub)
