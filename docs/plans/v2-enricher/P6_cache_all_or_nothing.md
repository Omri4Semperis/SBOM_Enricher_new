# P6: cache_all_or_nothing

**Your workspace.** This doc is writable. The other file you may edit is
`PLAN.md` — your table row, a concise Phase-notes reflection, and **Incoming
comments** in another phase's block. Never edit another phase's `P*` doc.

**Demo:** run a fixture twice with `cache_write` (then `cache_read`) set — the
second run reports a cache hit and skips inference/download/copyright for the
cached component.

**Goal:** Add the cross-run cache (ADR 0001): keyed on `component_name`, storing
the full enrichment record + LICENSE file. A hit short-circuits the whole
pipeline for that row; only fully-successful rows are written. Null/empty cache
paths silently skip.

## Entry criteria

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P5 Status is `done`
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed
- [ ] `git status --porcelain` → empty

## Context capsule

- `Config` (P1) has `cache_read` / `cache_write` (already `None` when
  null/empty). `pipeline.process_component` (P2–P5) fills the result object with
  `inferred_license_name`, `inferred_license_code_url`, `inferred_copyright`, and
  the downloaded file path. Confirm real names in prior Phase-notes.
- Locked cache rules (ADR 0001 + DECISIONS "Cross-run cache (simplified)"):
  - **Key:** `component_name` (already embeds version, e.g.
    `awesome.me@1.0.277`). Not the old `(lib_name, version, purl)` tuple.
  - **Stored per entry:** `inferred_license_name`, `inferred_license_code_url`,
    `inferred_copyright`, and the downloaded LICENSE file. Nothing else.
  - **Hit = all-or-nothing:** a hit on `component_name` returns the full record
    (name/url/copyright/file) and skips ALL inference + download + copyright for
    that row. No per-field partial reuse.
  - **Write only fully-successful rows:** license name known, a LICENSE file
    actually downloaded, and copyright extracted (not `UNKNOWN`). Any `UNKNOWN`
    value ⇒ not written, so a re-run retries exactly the failures.
  - **Null/empty path ⇒ silently skip** read/write. No prompt, no alert (drops
    old `console_input` confirmation flow).
- Old `knowledge/old_code/src/cache_store.py` is the reference (CSV index +
  license files on disk). It is heavier than needed — v2 key is a single
  string, no `(lib,ver,purl)` tuple, no `force_*` flags, no `outcome==OK`
  plumbing. Keep the storage shape minimal: a small index file
  (`cache.csv` or `cache.json`) mapping `component_name` → the three fields +
  the stored license filename, plus a `licenses/` subfolder in the cache dir.
- Cache lookup happens at the **start** of `process_component` (before
  inference); cache write happens at the **end**, only on full success. The
  restored file must be copied into the run's `licenses/` + `per_component/`
  just like a fresh download so outputs are identical to a non-cached run.
- Set a `from_cache` / `saved_by_cache` signal on the result object (or a
  per-phase cost marker) so P8 can compute `saved_by_cache_usd`. Keep it a plain
  flag now; P8 turns it into money.

## Files

**Touch (complete list):**

- `src/cache.py` — create: `read_cache(cache_read, component_name) ->
  CachedRecord | None`, `write_cache(cache_write, component_name, result)`
  (write only on full success), index + license-file storage, silent skip on
  `None` path.
- `src/pipeline.py` — edit: at start of `process_component` try `read_cache`;
  on hit, restore file into run dirs, fill result object, mark `from_cache`,
  skip stages; at end, `write_cache` on full success.
- `tests/test_cache.py` — create: round-trip write→read; `UNKNOWN` field ⇒ not
  written; `None` path ⇒ no-op read/write; hit restores file into run dir.

**Do not touch:** claude/gpt clients, download internals, audit (P7),
`knowledge/`.

## Tasks

### T1: cache store

- Steps: `src/cache.py` — index format (component_name → 3 fields + stored
  license filename), `read_cache` / `write_cache` with the full-success guard
  and silent `None` skip.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_cache.py -k
  store` → exit 0 (write then read returns the record; a record with any
  `UNKNOWN` is refused; `None` path returns `None` / writes nothing).
- Commit when green.

### T2: wire hit path (short-circuit)

- Steps: `src/pipeline.py` — read cache first; on hit copy the stored file into
  `licenses/{slug}` + `per_component/{slug}/`, fill the result object, set
  `from_cache`, skip inference/download/copyright, Story notes "cache hit".
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_pipeline.py -k
  cache` → exit 0 (seed a cache, run; assert inference/download/copyright NOT
  called and the file appears in the run dir).
- Commit when green.

### T3: wire write path

- Steps: `src/pipeline.py` — at end of a non-cached row, `write_cache` only when
  license name known + file downloaded + copyright not `UNKNOWN`.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_pipeline.py -k
  cache_write` → exit 0 (successful row written; row with `UNKNOWN` copyright
  not written).
- Commit when green.

## Validation gate

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. Fresh review of `git diff {baseline}..HEAD` by a `generalPurpose` readonly
   subagent (diff + this doc + over-engineering lens). Fix findings, re-run 1;
   ordered-behavior findings recorded not fixed.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- Test proving a second run hits cache and skips all three stages passes.

## Rollback

`git reset --hard {baseline hash from PLAN.md}`, Status `blocked` + one-line
reason in Phase-notes.

## Failure modes

1. Partial-record reuse creeping in → forbidden (ADR 0001); hit is all-or-
   nothing, miss runs the full pipeline.
2. Writing `UNKNOWN` rows to cache → guard the write; only full successes.
3. Prompting the user on null cache path → forbidden; silent skip.

## Anti-goals

- No `force_license_inference` / `force_copyright_extraction` / other cache
  flags — dropped in v2.
- No `(lib_name, version, purl)` key — `component_name` only.
- No stale-cache detection/invalidation — operator-owned (BACKLOG residual #2).
- Nothing beyond this doc's Tasks.

## If blocked

Set Status `blocked` in `PLAN.md` (Baseline + Updated), one-line reason in
Phase-notes, report and stop.

## On completion

1. Re-check Entry/Validation/Exit.
2. `PLAN.md`: Status `done`, Baseline + Updated.
3. Reflect into Phase-notes: cache index format + `read_cache`/`write_cache`
   signatures, the `from_cache` signal name P8 reads for `saved_by_cache_usd`.
4. Record full **Outcome** here (same shape as P1's).
