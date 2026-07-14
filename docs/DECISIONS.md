# SBOM Enricher v2 — Grilling Log

> Working log for the grilling session — the branch backbone plus confirmed
> decisions that will guide the later complex-plan creation. Each entry is
> either **[LOCKED]** (confirmed by Omri) or **[OPEN]** (still grilling).
>
> **Companion docs (per domain-modeling conventions):**
>
> - `CONTEXT.md` (repo root) — the glossary of domain terms. Sole home of
> terminology; this log references terms, it doesn't define them.
> - `docs/adr/` — Architecture Decision Records for durable, hard-to-reverse
> decisions. Offered at session close, not written mid-grill.

## Subject

Enrich a component CSV (`component_name` + `purl`) with license name, a
reachable/downloadable LICENSE file URL (+ the downloaded file), and the
copyright statement found in that file. Optionally compare against supplied
ground-truth columns and score the run.

- Entrypoint: `(.venv) python src/main.py`, auto-loads `configs/default.json`.
- Enrichment is the product; comparison + scoring are an optional **audit mode**
active only when ground-truth columns are present.

---

## Branch status

- [x] Goals and non-goals
- [ ] Scope boundaries

- [~] Input / output contract (identifiers + parsing locked; column order open)

- [x] Enrichment pipeline (inference → download → copyright)
- [x] Equality / comparison
- [x] Scoring (`score.csv`)
- [~] LLM contracts (license + copyright schemas LOCKED; equality-judge schema open)
- [x] Failure handling (retry/backoff + run-level continue/fail-fast)
- [x] Config / ops (cache, workers, `default.json`, key naming, progress bar)
- [ ] Security / credentials
- [ ] Open risks / deferred

- [~] Domain terms (glossary seeded in `CONTEXT.md`, growing)

- [ ] Decision recording (ADRs offered at close)

---

## Decisions

### Goals & non-goals — [LOCKED]

- **Primary goal:** for every input row produce three enrichment fields +
the downloaded LICENSE file:
  - `inferred_license_name` — e.g. `MIT`, `GPL-3.0`.
  - `inferred_license_code_url` — reachable, downloadable URL to the LICENSE
  file, ideally from the raw publication of the component. The file is
  actually downloaded.
  - `inferred_copyright` — the copyright statement found **in the downloaded
  file**. No download ⇒ copyright cannot be inferred.
- **Secondary goal (audit mode):** when input already carries
`license_name` / `license_code_url` / `copyright`, emit equality columns and
scoring.
- **Non-goals (this build):** vulnerability data, dependency graphs, a UI, and
reusing/porting the old `knowledge/old_code/` system (inspiration only).

### Input validation (fail-fast) — [LOCKED]

- Input **must** contain `component_name` and `purl` columns — else fail fast.
- `component_name` column **must** have no duplicates — else fail fast.

### Run output layout — [LOCKED]

On run start, create an output directory:
`{output_base}/{yyyymmdd_HHMMSS}_{model_short}_{n_components}/`

Contents:

```txt
input/            copy of the input file + copy of the run config (for re-creation)
licenses/         flat; one downloaded LICENSE per component, named by component
per_component/{component_name}/
                  raw responses from all models (.json if parseable, else .txt),
                  plus the downloaded license file
results_{model_short}_{n}.csv           input + inferred_* + is_eq_* columns
results_{model_short}_{n}_extended.csv  everything: raw responses per LLM,
                                        normalized + un-normalized values,
                                        approximate costs, cache hit/miss, per phase
summary.json      run info: paths, run id, run name (if config supplies one),
                  model, workers, components count, start/end time (UTC)
score.csv         hit/mismatch/unknown tally (audit mode only)
```

### Identifiers & parsing — [LOCKED]

- `component_name` parsing: strip whitespace and leading/trailing `@`, then
`rpartition("@")` on the last remaining `@` → (`lib_name`, `version`).
Example: `awesome.me@1.0.277` → lib_name `awesome.me`, version `1.0.277`.
- `purl` is the **primary** identifier passed to the license inference (Claude)
call; `lib_name`/`version` are secondary human-readable context. (Mirrors the
old code, which fed lib_name + version + purl to the inferencer and also used
the purl as the deterministic key for npm/unpkg license-file fallback.)
- `component_name` is the dedup key and the naming key for `licenses/` and
`per_component/` directories.
- Directory/file names use a **sanitized** `component_name` (filesystem-unsafe
chars replaced). The raw `component_name` + `purl` are preserved inside each
`per_component/` dir (e.g. a small `meta.json`) so the mapping is never lost.

### License inference step — [LOCKED]

- License inference is a **single Claude call** returning a JSON object with
`license_name`, `license_code_url`, and a short `reasoning` field. Claude uses
its own `WebSearch`/`WebFetch` tools to find the raw LICENSE URL.
- The old code's **consistency judge** (a GPT-4.1 self-check on Claude's license
reasoning) is **dropped for now**. GPT-4.1's only role in this build is the
equality judge (audit mode).
- Claude returns `UNKNOWN` rather than guessing when it can't determine a
license (feeds the `unknown` scoring outcome).
- **Note for later:** if license-inference scores look weak (many mismatches),
restoring the consistency check is the lever to trade mismatches for
unknowns (reduce wrong guesses at the cost of more "don't know").

### License-file download — [LOCKED]

- Download Claude's `inferred_license_code_url`.
- Always **rewrite viewer URLs to raw** (`github.com/.../blob/...` →
`raw.githubusercontent.com`, GitLab `/-/blob/` → `/-/raw/`) and **reject
HTML/generic-template responses** (don't save site chrome as "license text").
- On failure, **fall back to purl-derived candidate URLs** (npm/unpkg:
`LICENSE`, `LICENSE.md`, …).
- `inferred_license_code_url` is set to the **URL that actually worked**
(resolved URL), not a dead URL Claude returned. The original Claude URL and
every attempted source are preserved in `results_extended.csv`.
- A per-component record must capture **why** each download choice/source was
made (see Story file below).

### Per-component "story" file — [LOCKED]

Each `per_component/{component_name}/` dir gets a plain-text, human-readable
**story**: a step-by-step narrative of everything done to enrich that component
— what was tried, what each LLM responded, fallbacks taken, number of tries,
what crashed, and how long steps took. Written for a human debugging one
component, not for machines.

### Copyright extraction step — [LOCKED]

- Copyright is extracted **only from a successfully downloaded LICENSE file**,
by an LLM (GPT-4.1). Returns JSON
`{ "copyright": "<verbatim statement, or UNKNOWN>", "reasoning": "<one sentence>" }`
(see the locked LLM contract below — supersedes the earlier `found: bool` idea).
- The value is the **full copyright statement as it appears** in the file
(verbatim, trimmed) — e.g. `Copyright (c) 2020 Jane Doe` — not just the holder.
- **No fallbacks.** File missing, or file has no holder ⇒ `inferred_copyright`
= `UNKNOWN`.

### Equality / comparison — [LOCKED]

- `is_eq_*` columns hold only `TRUE`/`FALSE`. An `is_eq_*` column is added only
for an item whose Ground Truth column is supplied.
- **License name** and **copyright** use the three-rung ladder:
identical → normalized-match (lowercase + special-char normalization, e.g.
`ï¿`, `(c)`) → GPT-4.1 judge → else FALSE.
- `**is_eq_url` is content-based**, not string-based: judged on whether the
inferred URL and the ground-truth URL **resolve to the same LICENSE content**.
Both URLs are downloaded and their content compared with the same ladder
shape, starting with a **byte comparison**:
byte-identical → normalized-match (whitespace/BOM/line-endings/case) →
GPT-4.1 judge ("is this the same license text?") → else FALSE.
- `**is_eq_url = TRUE` requires both files to download successfully and match.**
If the ground-truth URL won't download (404/HTML/timeout), or our inferred URL
didn't download, `is_eq_url = FALSE`. The reason (e.g. `gt_url_download_failed`)
is recorded in `results_extended.csv` so FALSE is never ambiguous.

### Scoring (`score.csv`) — [LOCKED]

- Each inference item is graded as one of:
  - **hit (h)** — inferred value matches ground truth.
  - **mismatch (m)** — inferred a wrong value.
  - **unknown (u)** — we didn't know and didn't guess wrong.
- `score.csv` is a **tally** of item-grade combinations with a `Count` column.
- Only items that have a supplied ground-truth column are graded/columns.
- Row count max = `3 ^ (# ground-truth items provided)`; rows with `Count == 0`
are omitted. (All three ⇒ up to 27 rows; two ⇒ up to 9; etc.)
- If no ground-truth columns are supplied, `score.csv` is skipped entirely.
- Schema (only columns for graded items; values ∈ {h, m, u}):

```txt
license_name,license_code_url,copyright,Count
h,h,h,105
h,m,u,42
...
```

- No `component_name`/`purl` columns in `score.csv` — per-component grades live
in `results_extended.csv` for traceability.

### Cross-run cache (simplified) — [LOCKED]

Keep the *idea* of a cross-run cache but strip the old system's complexity.

- **Key:** `component_name` (which already embeds version, e.g.
`awesome.me@1.0.277`), not the old `(lib_name, version, purl)` tuple.
- **Stored per entry:** `inferred_license_name`, `inferred_license_code_url`,
`inferred_copyright`, and the downloaded LICENSE file. Nothing else.
- **Config knobs:** only the `cache_read` and `cache_write` paths already in
`default.json`. **No** `force_license_inference` / `force_copyright_extraction`
and no other cache flags.
- **Null/empty path handling:** if `cache_read` (or `cache_write`) is null or
empty, silently skip reading from / writing to the cache. **No user prompt or
alert** (drops the old `console_input` confirmation flow).
- **Hit granularity: all-or-nothing.** A cache hit on `component_name` means
"this component is done" — return the full cached record (license/url/
copyright/file) and skip *all* inference + download for that row. No
per-field partial reuse.
- **Only fully-successful rows are written** to the cache: license name known,
a LICENSE file actually downloaded, and copyright extracted (not `UNKNOWN`).
Any row with an `UNKNOWN` value is left out, so a re-run retries exactly the
failures and skips the successes. (Replaces the old `outcome==OK` filter.)

### Concurrency (workers) — [LOCKED]

- **One `workers` knob**, one pool. A worker takes a component and runs its
**full pipeline end-to-end** (infer → download → copyright) before picking up
the next. No per-stage pools (drops the old inference/fetch/judge/copyright-
infer split). KISS.
- Benefits: one number to configure; a component's Story is a clean sequential
narrative; a slow/hung component ties up only its own worker.

### `default.json` field set — [LOCKED]

Complete config schema for v2 (old set minus the dropped `force_*` knobs):

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

- `input_file_path` — required; fail-fast if missing/invalid.
- `output_base_path` — required; run dir
`{output_base_path}/{yyyymmdd_HHMMSS}_{model_short}_{n}/` created under it.
- `run_name` — optional (null); recorded in `summary.json` when set.
- `model` — Claude model for license inference; validated against a **fixed
allow-list** (old `MODEL_CHOICES`) so a typo fails fast instead of burning a
run. GPT-4.1 (copyright/equality) is **not** a config field — fixed for now
(revisit under LLM contracts).
- `workers` — the single pool size; keep the old 1–30 bound.
- `cache_read` / `cache_write` — nullable paths; null/empty ⇒ skip silently.
- **Naming — [LOCKED]:** keep the on-disk key names exactly as they are
(`input_file_path`, `output_base_path`, `run_name`, `model`, `workers`,
`cache_read`, `cache_write`). No renaming/suffix-normalization — churn for no
functional gain.

### Progress display — [LOCKED]

- Keep the old code's **live progress bar** (block-glyph bar +
`done/total`), extended with an **ETA**. Example shape:
  ```py
  def progress_bar(done: int, total: int, width: int = 35) -> str:
      filled = int(width * done / total) if total else 0
      return f"[{'█' * filled}{'░' * (width - filled)}] {done}/{total}"
  ```
- ETA derived from elapsed time and completed-component rate.

### Retry / backoff policy — [LOCKED]

Two distinct LLM-call failure kinds, treated differently:

- **Failed communication** (network error, timeout, HTTP 429/5xx, Claude CLI
non-zero exit): **retry, 3 attempts total** (initial + 2 retries), *only* on
genuinely transient signals. A hard 4xx (401/403 auth, 404) is **not**
retried — fail that stage immediately.
  - **Backoff (jittered):** retry #1 after a **fixed** async sleep; retry #2
  after a **random** async sleep within a range. The randomness prevents
  synchronized retries across workers from re-bombarding a source that failed
  because of too many requests. (`asyncio.sleep`, non-blocking.)
- **Failed parse** (LLM responded but output isn't the requested JSON): **retry,
2 attempts total** (initial + 1 retry). One retry covers LLM non-determinism;
beyond that it's a systematic prompt/format problem, so stop and record the
raw response rather than looping and burning cost.
- **After retries exhaust:** the stage fails closed (license/copyright ⇒
`UNKNOWN`), reason recorded in the Story + `results_extended.csv`; per the
workers decision only that one component is affected.
- **Values — [LOCKED]:** transient retry #1 = fixed **2s**; transient retry #2
= uniform random in **[3s, 8s]**; parse retry = fixed **1s** (no jitter —
parse failures aren't a server-load problem). Applies to both the Claude
license call and the GPT-4.1 copyright call.
- **Hard-coded constants**, not `default.json` knobs — operational tuning, not
per-run parameters; keeps the config surface minimal.

### Failure handling — run level — [LOCKED]

- **Startup/config failures** (bad config, missing input file, duplicate
`component_name`, no auth): **fail-fast** before any work runs.
- **Per-component stage failures at runtime** (after retries — can't infer
license, can't download, can't extract copyright): **always continue.** The
component fails closed to `UNKNOWN`, gets its Story + `results_extended.csv`
reason, and the run proceeds. One bad package never discards the work/cost of
the good ones.
- **No circuit-breaker for v2.** A systemic failure (e.g. every call 401)
simply yields an all-`UNKNOWN` run, made obvious by the progress bar; the user
can Ctrl-C. Add a threshold/circuit-breaker later only if it actually bites.

### LLM contract — license inference (Claude) — [LOCKED]

Single full Claude call, web tools on, returning exactly three fields (all
always present):

```json
{
  "license_name": "<SPDX id / shorthand, or UNKNOWN>",
  "license_code_url": "<raw downloadable LICENSE URL, or empty string>",
  "reasoning": "<concise sources-checked summary>"
}
```

- Keys renamed from old code (`license`→`license_name`, `license_url`→
`license_code_url`) to match the locked domain terms; map 1:1 to the
`inferred_*` output columns.
- `license_name = "UNKNOWN"` is the "couldn't determine" signal (feeds the
`unknown` scoring outcome).
- `reasoning` always required — feeds the Story and is the debugging lifeline.
- No "request only missing fields" branching — always ask for all three.
- **No `confidence` field** — uncertainty is expressed via the `UNKNOWN`
sentinel; an unused confidence number is speculative complexity.

### LLM contract — copyright extraction (GPT-4.1) — [LOCKED]

Input: the downloaded LICENSE file **text only**. Output:

```json
{ "copyright": "<verbatim statement, or UNKNOWN>", "reasoning": "<one sentence>" }
```

- Option (A): the `UNKNOWN` sentinel replaces a redundant `found` boolean;
consistent with the license-inference contract (sentinel + always a
`reasoning`). `reasoning` feeds the Story. Maps to the `inferred_copyright`
column. No fallbacks (locked): no file / no holder ⇒ `UNKNOWN`.

## Open questions (next up)

- Input/output contract details: exact `results.csv` column order, encoding.
- Equality/normalization rules and the LLM-judge boundary (mostly locked).
- LLM contracts (JSON schemas, which model per role).
- Failure handling per stage (fail-fast vs continue) + the retry/backoff item
above.
- Security/credentials (Azure `DefaultAzureCredential`, Claude CLI auth).
- Scope boundaries; open risks / deferred; ADRs at close.

