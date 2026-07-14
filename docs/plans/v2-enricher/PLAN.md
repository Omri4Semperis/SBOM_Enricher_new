# Plan: v2-enricher

**Live document.** Unlike the old design, this file is written to during
execution. The executor of phase N may edit **only two files**: its own
`P{N}_{...}.md` doc and this `PLAN.md`. It updates its row in the phase
table, reflects concise notes into its own per-phase block, and leaves
**Incoming comments** in *another* phase's block here when it discovers
something that phase must know. It never edits another phase's `P*` doc.

**Execution:** one phase per fresh session via the `complex-plan-implement-phase`
skill. Fallback without that skill: pick the lowest-numbered phase whose
**Depends on** entries are all `done` in the table below and whose own Status
is `pending`; then follow that phase doc top to bottom — its Entry criteria,
Tasks, Validation gate, Exit criteria, and On completion sections are the
complete procedure. Read this whole `PLAN.md` first for cross-phase context
and any Incoming comments left in your phase's block.

## Goal

Build SBOM Enricher v2 end to end from the locked decisions: for each input
CSV row (`component_name` + `purl`) produce `inferred_license_name`, a
resolved downloadable `inferred_license_code_url` + the downloaded LICENSE
file, and file-only `inferred_copyright`. When ground-truth columns are
present (audit mode), also emit `is_eq_*` verdicts and `score.csv`. The old
`knowledge/old_code/` system is inspiration only — v2 exists because v1 was
sloppy and over-complex, so every phase takes the lazy path that satisfies the
decision, nothing more.

## Context

- **Authority (do not re-litigate):** `docs/DECISIONS.md` (all `[LOCKED]`),
  `docs/CONTEXT.md` (glossary), ADRs `0001` (cache all-or-nothing), `0002`
  (URL equality by content), `0003` (copyright file-only). Deferred work lives
  in `docs/BACKLOG.md` and is **out of scope** for every phase here.
- **Language:** Python 3.13, stdlib-first. Deps already installed in `.venv`:
  `openai`, `azure-identity`, `azure-ai-projects`, `requests`, `pypdf`.
  P1 adds `pytest` to the venv. No pandas (stdlib `csv` only).
- **Layout:** all new source under `src/` (flat package, run as
  `python src/main.py` auto-loading `configs/default.json`). Tests under
  `tests/`. Both dirs currently empty.
- **Two live LLM providers:** Claude via local `claude` CLI subprocess
  (license inference, the one configurable model); GPT-4.1 via fixed Azure
  deployment `gpt-4.1-limitless` with `DefaultAzureCredential` (copyright
  extraction + equality judge). Example call shapes:
  `knowledge/query_example_claude.py`, `knowledge/query_example_gpt-4-1.py`.
- **Old code is reference-only, never imported at runtime.** Cite it for
  prompt wording and tricky bits (viewer→raw URL rewrite, npm purl parsing);
  do not port its structure.
- **Vertical slices:** P2 stands up a runnable stub pipeline (writes
  `UNKNOWN` rows) before any paid LLM call; later phases fill real behavior.

## Phases

| Phase                                                             | Purpose                                                              | Depends on | Status  | Baseline | Updated |
| -                                                                 | -                                                                    | -          | -       | -        | -       |
| [P1: scaffold_and_config](./P1_scaffold_and_config.md)            | pytest in venv, `src` package, load + validate `default.json`        | -          | done | c221171 | 2026-07-14 |
| [P2: input_run_dir_stub](./P2_input_run_dir_stub.md)              | CSV validate + parse, run dir + input copies, stub worker pipeline   | P1         | done | f65cd87 | 2026-07-14 |
| [P3: license_inference](./P3_license_inference.md)                | Claude client + license JSON contract + retry, wired into pipeline   | P2         | done | 234411c | 2026-07-14 |
| [P4: license_download](./P4_license_download.md)                  | viewer→raw rewrite, HTML reject, npm/unpkg fallback, save files      | P3         | done | f7b3f36 | 2026-07-14 |
| [P5: copyright_extraction](./P5_copyright_extraction.md)          | fixed GPT-4.1 client, file-only copyright (ADR 0003)                 | P4         | done | 45d6cfd | 2026-07-15 |
| [P6: cache_all_or_nothing](./P6_cache_all_or_nothing.md)          | cross-run cache keyed on `component_name`, full-success-only (0001)  | P5         | done | 63fb57c | 2026-07-15 |
| [P7: audit_equality_score](./P7_audit_equality_score.md)          | `is_eq_*` triplets, ladders, URL content-sameness (0002), score.csv  | P5         | done | e022742 | 2026-07-15 |
| [P8: ops_preflight_progress_summary](./P8_ops_preflight_progress_summary.md) | preflight, progress+ETA, extended CSV, summary.json      | P6, P7     | in progress | 2d0e27a | 2026-07-15 |

Filenames use `P{N}_{snake_case_title}.md`. "Depends on" lists phase ids or "-".

## Test commands

| Purpose    | Command                                    | Expected                                             |
| -          | -                                          | -                                                    |
| full suite | `.\.venv\Scripts\python.exe -m pytest -q`  | exit 0, all passed (baseline: pytest not yet installed — P1 installs it and adds the first tests) |

No separate typecheck/lint gate in this repo; the suite is the only gate.

## Phase notes

### P1: scaffold_and_config

- **For other phases:** exposes `src/config.py` with `load_config(path) -> Config`
  (a frozen dataclass carrying `input_file_path`, `output_base_path`,
  `run_name`, `model`, `workers`, `cache_read`, `cache_write` as resolved
  `Path`/`str`/`int`/`None`). Fail-fast raising `SystemExit` with a one-line
  message on: unknown `model` (allow-list), `workers` outside 1–30, missing
  required paths. Model allow-list constant `MODEL_CHOICES` lives here. Nullable
  `cache_read`/`cache_write` resolve to `None` when null/empty.
- **Notes:** Done. `Config` frozen fields: `input_file_path: Path`,
  `output_base_path: Path`, `run_name: str | None`, `model: str`,
  `workers: int`, `cache_read: Path | None`, `cache_write: Path | None`.
  `MODEL_CHOICES` = haiku-4-5, sonnet-4-6, sonnet-5, opus-4-6, opus-4-7,
  opus-4-8. `load_config(path) -> Config`; paths via `REPO_ROOT`;
  `SystemExit` one-liners. pytest 9.1.1 in `.venv` only. T1: 0-tests →
  pytest exit 5 (doc said 0). Review PASS (record-only: conftest sys.path,
  helpers, unused `__future__`).
- **Incoming comments:**

### P2: input_run_dir_stub

- **For other phases:** exposes the pipeline skeleton — `src/main.py` with
  `run(config)`; a worker pool of size `config.workers` where each worker runs
  one component end to end. Component parsing: strip + strip leading/trailing
  `@`, `rpartition("@")` → `(lib_name, version)`. Sanitized slug map built for
  the whole input up front; slug collision → fail-fast. Row records flow
  through a mutable per-component result object that later phases fill; P2
  leaves every inferred field `UNKNOWN`. Story file writer and streaming
  `results_{model_short}_{n}.csv` (`utf-8-sig`, `csv.DictWriter`) live here.
  Column order per DECISIONS "Main results.csv column order".
- **Notes:** Done. Signatures: `input_csv.read_components(path) -> list[Component]`
  (`component_name`, `purl`, `lib_name`, `version`, `slug`, `extras`);
  `run_dir.model_short(model) -> str`, `results_csv_name(model, n) -> str`,
  `create_run_dir(config, components) -> Path`; `pipeline.ComponentResult`
  (mutable: `component` + three `inferred_*` default `"UNKNOWN"`);
  `async process_component(comp, run_dir) -> ComponentResult`;
  `async run_workers(config, components, run_dir, writer) -> list[ComponentResult]`
  (Semaphore + as_completed, streams rows); `append_story(run_dir, slug, line)`
  writes `per_component/{slug}/story.txt`; `main.run(config) -> Path`;
  `main.py [config.json]` optional argv. Review PASS (lean). Deviations: config
  snapshot serialized to `input/config.json` (no config path in signature);
  `runs/` untracked (see P8 Incoming).
- **Incoming comments:**

### P3: license_inference

- **For other phases:** exposes `src/claude_client.py` `infer_license(purl,
  lib_name, version, model) -> dict` returning `{license_name,
  license_code_url, reasoning}` (contract in DECISIONS "LLM contract — license
  inference"). Retry policy helper (transient 3 attempts, parse 2 attempts,
  locked backoff values) lives in `src/retry.py` and is reused by P5. Sets
  `inferred_license_name` + `inferred_license_code_url` on the result object.
- **Notes:** Done. `async infer_license(...) -> dict` with contract keys plus
  `attempts` (Story-only). Fail-closed: `UNKNOWN` / `""` / reason.
  `async with_retries(fn, *, transient_attempts=3, parse_attempts=2, classify)
  -> T` in `src/retry.py` (hard re-raises; sleeps 2s then U[3,8] / parse 1s).
  Prompts in `src/prompts.py`: `license_prompt(...) -> (str, dict)` +
  `LICENSE_SCHEMA`. Pipeline: `process_component(comp, run_dir, model)` —
  gained `model` vs P2. Review PASS (lean). Tests use `asyncio.run` (no
  pytest-asyncio).
- **Incoming comments:**

### P4: license_download

- **For other phases:** exposes `src/download.py` `fetch_license_file(url, purl,
  dest_dir) -> DownloadResult` (resolved URL + saved path, or failure reason).
  Viewer→raw rewrite + HTML/template reject + npm/unpkg purl fallback. Writes
  `licenses/{slug}.<ext>` and a copy in `per_component/{slug}/`. Sets
  `inferred_license_code_url` to the URL that actually worked. The saved file
  path is what P5 (copyright) and P6 (cache) consume.
- **Notes:** Done. `async fetch_license_file(claude_url, purl, dest_dir, slug)
  -> DownloadResult` with fields `resolved_url`, `saved_path: Path | None`,
  `error`, `original_url`, `attempts: list[str]`, `ok` property.
  `ComponentResult` gained `license_file_path` (P5/P6 consume),
  `download_attempts`, `original_license_url` (P8 extended CSV). Failure leaves
  Claude's URL on `inferred_license_code_url` and `license_file_path=None`.
  Review PASS (shrinks applied; `_HttpFail` adapter + filename list recorded
  as ordered complexity).
- **Incoming comments:**

### P5: copyright_extraction

- **For other phases:** exposes `src/gpt41_client.py` (fixed deployment,
  `DefaultAzureCredential`) and `extract_copyright(license_text) -> dict`
  returning `{copyright, reasoning}`. Reads ONLY the downloaded file (ADR
  0003); no file ⇒ `inferred_copyright = UNKNOWN`. The GPT-4.1 client here is
  reused by P7's equality judge — expose it as a small reusable class.
- **Notes:** Done. `Gpt41Client.complete_json(system_prompt, user_prompt) ->
  dict` with `with_retries`; Azure constants live in `src/gpt41_client.py`
  (`AZURE_ENDPOINT`, `GPT41_DEPLOYMENT=gpt-4.1-limitless`, `AZURE_API_VERSION`,
  `AZURE_TOKEN_SCOPE`). `async extract_copyright(license_text) -> dict` in
  `src/copyright.py` ({copyright, reasoning}; placeholder/empty/fail →
  UNKNOWN). Pipeline reads `license_file_path` only. Review PASS; dropped
  unused `TransientFailure`. Deviation: unrelated commit `4f44847` lint-fixed
  other phase `P*` docs mid-phase (outside P5 Touch; not reverted).
- **Incoming comments:**

### P6: cache_all_or_nothing

- **For other phases:** exposes `src/cache.py` — read keyed on
  `component_name`, returns full record (name/url/copyright/file) or nothing
  (ADR 0001); write only rows with no `UNKNOWN` and a downloaded file. Null/
  empty cache paths silently skip. A cache hit short-circuits P3/P4/P5 for that
  row. P8 reads `saved_by_cache_usd` signals set here.
- **Notes:** Done. Index `cache.csv` + `licenses/` under the cache dir.
  `read_cache(cache_read, component_name) -> CachedRecord | None`;
  `write_cache(cache_write, component_name, result) -> bool`;
  `restore_license_file(record, run_dir, slug) -> Path`. Cached license
  filenames are `quote(component_name, safe="@.-+")` + ext (avoids slug
  collisions across inputs). `ComponentResult.from_cache: bool` — P8 reads
  this for `saved_by_cache_usd`. Hit at start of `process_component`; write
  at end on full success. Review PASS; applied unique-filename fix + dropped
  unused `threading.Lock` / public `is_full_success`. Deviation: T2+T3 wired
  in one commit.
- **Incoming comments:**

### P7: audit_equality_score

- **For other phases:** exposes `src/equality.py` — per-item `is_eq_*` verdicts
  (TRUE/FALSE only), name/copyright three-rung ladder, URL content-sameness
  ladder (ADR 0002: byte → normalize → GPT-4.1 judge, both downloads must
  succeed else FALSE), and `score.csv` tally writer. Only emits columns/grades
  for items whose ground-truth column is supplied. Reuses P5's GPT-4.1 client
  for the judge (uniform `{verdict, reasoning}` schema).
- **Notes:** Done. Audit detected via `detect_gt_columns(extras)` from input
  header (`license_name` / `license_code_url` / `copyright`). `ResultsWriter`
  rebuilds locked triplets (GT→inferred→is_eq; collapse when GT absent;
  other extras at end). Equality: `compare_name` / `compare_copyright` /
  `compare_url_content` → `EqResult(verdict, reason)`; wired in
  `pipeline.apply_equality` after enrichment (incl. cache hits).
  `ComponentResult` fields for P8 extended CSV: `is_eq_*`,
  `eq_license_name_reason` / `eq_license_code_url_reason` /
  `eq_copyright_reason`, `grades` (`h`/`m`/`u` per GT item).
  `scoring.write_score_csv(path, results, gt_columns)` → `score.csv` or None.
  Review PASS; applied unused-property / dead-branch shrinks.
- **Incoming comments:**
  - From P3: audit inputs already flow through today. `read_components`
    (`src/input_csv.py`) puts every non-`component_name`/`purl` column into
    `extras`, and `ResultsWriter` (`src/results_csv.py`, `BASE_COLUMNS` +
    extras) appends them at the END. So `default.json`'s `input/tiny.csv` (has
    GT `license_name`, `license_code_url`, `copyright`) currently writes
    `...,inferred_copyright,license_name,license_code_url,copyright` — GT cols
    dumped after the inferred block, no `is_eq_*`. P7 must recognize the GT set
    and rebuild the LOCKED interleaved triplet order (GT → inferred → is_eq per
    item; DECISIONS "Main results.csv column order"), not rely on the
    extras-at-end passthrough. Verified against run
    `runs/20260714_232633_ClaudeOpu-4-8_2`.

### P8: ops_preflight_progress_summary

- **For other phases:** terminal phase. Startup dual-provider preflight
  (3 deterministic attempts, no jitter → fail-fast); live progress bar + ETA;
  `results_{model_short}_{n}_extended.csv` (all raw responses, costs, cache
  hit/miss, per-phase); `summary.json` (paths, run id/name, model, workers,
  counts, UTC start/end, per-phase cost + timing buckets). Pricing table is a
  source constant, not config.
- **Notes:**
- **Incoming comments:**
  - From P2: add `runs/` to `.gitignore` (P2 exit demo created untracked
    `runs/`; `.gitignore` was outside P2 Touch list). See P2 Outcome.
  - From P7: extended CSV should surface per-component `is_eq_*` reasons
    (`eq_license_name_reason`, `eq_license_code_url_reason`,
    `eq_copyright_reason` — e.g. `gt_url_download_failed` / `judge:…`) and
    `grades` (`h`/`m`/`u` dict keyed by GT item). `score.csv` already written
    by `scoring.write_score_csv`; do not re-grade from scratch unless needed.

## On completion

Only after every phase shows `done` in the table above, in this order:

1. Graduate durable decisions out of the plan: anything in a Phase-notes block
   or a phase doc that a future maintainer must know goes to an ADR (invoke the
   `domain-modeling` skill; if unavailable, a dated note in the repo's docs).
2. Stamp the top of this file: `COMPLETED {YYYY-MM-DD} — historical record,
   not current truth`.
3. Move the whole plan directory to `docs/plans/archive/v2-enricher/`.

Stale plan docs poison future agents — archive, don't keep.
