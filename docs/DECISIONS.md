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
- [x] Scope boundaries

- [x] Input / output contract (identifiers, parsing, layout, column order, encoding LOCKED)

- [x] Enrichment pipeline (inference → download → copyright)
- [x] Equality / comparison
- [x] Scoring (`score.csv`)
- [x] LLM contracts (license + copyright + equality-judge schemas + model fixed-vs-configurable LOCKED)
- [x] Failure handling (retry/backoff + run-level continue/fail-fast)
- [x] Config / ops (cache, workers, `default.json`, key naming, progress bar)
- [x] Security / credentials
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

### LLM contract — equality judge (GPT-4.1) — [LOCKED]

The third rung of the equality ladder for **all three** comparison kinds
(license name, copyright, URL-content sameness). Output:

```json
{ "verdict": "TRUE" | "FALSE", "reasoning": "<one sentence>" }
```

- **One uniform output schema across all three kinds** — the *prompt* varies
by kind (the old code's `kind` param), the *output shape* does not.
- `verdict` uses **`TRUE`/`FALSE`** (not the old bare `YES`/`NO`) so it maps
1:1 to the `is_eq_*` column and filters cleanly in Excel during later
analysis.
- Replaces the old bare-text `YES`/`NO` verdict with the same
`{ value, reasoning }` shape as the other two contracts. `reasoning` feeds
the Story + `results_extended.csv`, so a `FALSE` from the judge is never
ambiguous.
- The judge **always commits** to `TRUE`/`FALSE` — no `UNKNOWN` here (a
missing/failed ground-truth download resolves to `is_eq_url = FALSE` upstream
before the judge is ever called; see the Equality/comparison decision).

### Model: fixed vs configurable per role — [LOCKED]

- **Claude (license inference) is the one configurable model** — the `model`
knob in `default.json`, validated against the fixed allow-list. It does the
main heavy lifting, so it's deliberately swappable to compare **cost, time,
and accuracy** across Claude models run-to-run.
- **GPT-4.1 (copyright extraction + equality judge) is fixed** — a hard-coded
Azure deployment name (`gpt-4.1-limitless`), **not** a `default.json` field.
It's auxiliary plumbing, not the thing being benchmarked; keeps the config
surface minimal. Promoting it to a knob later is a trivial change if a second
GPT deployment ever appears.

### Main `results.csv` column order — [LOCKED]

`results_{model_short}_{n}.csv` = input + `inferred_*` + `is_eq_*`, ordered so
each item's **ground-truth → inferred → verdict** triplet sits together
(reads across three adjacent columns in Excel):

```txt
component_name, purl,
license_name,      inferred_license_name,      is_eq_license_name,
license_code_url,  inferred_license_code_url,  is_eq_license_code_url,
copyright,         inferred_copyright,         is_eq_copyright
```

- **Fixed leading columns:** `component_name`, `purl`.
- **Per-item triplet** (one block per enrichment item): the ground-truth
column (only if supplied) → the `inferred_*` column (always) → the `is_eq_*`
column (only if that item's ground-truth was supplied).
- **Degradation:** no ground truth for an item ⇒ that item collapses to just
its `inferred_*` column (no GT column, no `is_eq_*`). Non-audit run (no GT at
all) ⇒ only `component_name, purl, inferred_license_name,
inferred_license_code_url, inferred_copyright`.
- **Assumption (flag if wrong):** any *extra* passthrough input columns
outside this known set are preserved at the **end**, in original input order.
- The exhaustive per-LLM / cost / cache / raw-response columns live in
`results_{model_short}_{n}_extended.csv`, not here.

### CSV encoding & writer — [LOCKED]

- **Encoding:** `utf-8-sig` (UTF-8 + BOM) so Excel opens license/copyright
text (accents, `©`, curly quotes) correctly on double-click without the
import wizard. Applies to all CSVs (`results`, `results_extended`, `score`).
- **Writer:** stdlib `csv.DictWriter` with `newline=""` (→ `\r\n`). No pandas
dependency — this is row-writing, and `DictWriter` streams rows as workers
finish, so partial results survive a Ctrl-C/crash (fits "one bad component
never discards the good ones"). `score.csv` is a small tally — same tool.
- Decision **delegated to the assistant** by Omri ("write plain csv, easiest
way, any package"); recorded here so the later plan doesn't re-litigate it.

### Scope boundaries — per-row purl & ecosystem — [LOCKED]

- **Empty/malformed `purl` cell** (column present, value missing on a row):
**does not fail the run** — the row proceeds under the per-component continue
policy. Claude still gets `lib_name`/`version` context, but the deterministic
npm fallback (needs a purl) is skipped, so the row likely resolves to
`UNKNOWN`; the Story records "no purl → degraded inference." Fail-fast stays
reserved for structural problems (missing column, duplicate key).
- **Deterministic download fallback is npm/unpkg only** for v2. Every other
ecosystem (PyPI, Maven, Cargo, …) relies purely on Claude's `WebSearch`/
`WebFetch` to locate the raw LICENSE URL. Broadening the deterministic
fallback per ecosystem is explicitly **out of scope** (a "later" lever, like
restoring the consistency judge).

### Scope boundaries — input format — [LOCKED]

- **CSV only** for input; no `.xlsx`/`.json`/TSV ingestion (export to CSV
first). Matches the CSV-locked output side and keeps parsing to the stdlib
`csv` reader.
- **One input file per run** (the single `input_file_path`); no directory/glob
multi-file batching.

### Security / credentials — [LOCKED]

- **No secrets in our code or `default.json`.** Azure roles (GPT-4.1 copyright
extraction + equality judge) authenticate via `DefaultAzureCredential`
(`az login` locally / managed identity in CI). Claude authenticates via the
local `claude` CLI's own logged-in session (subprocess). The hard-coded
endpoint/deployment URLs (`ai-foundry-rnd-dev...`, `gpt-4.1-limitless`, the
equality-judge agent name/version) are **non-secret** and stay in source.
- **No token/credential is ever written** to Stories, raw-response files,
`summary.json`, or any CSV.
- No API-key / env-var auth path for v2 — ambient credential providers only.

### Startup connectivity preflight → fail-fast — [LOCKED]

- Before spawning any workers, **probe both LLM providers** — a trivial
`claude` invocation and an Azure token acquisition
(`DefaultAzureCredential.get_token`, and/or a minimal GPT-4.1 call). If a
provider is unreachable/unauthenticated after the preflight, **fail-fast**
with a clear message rather than burning a full run of 401s/timeouts.
- **Preflight is itself retried** — this check can make or break a whole run,
so a single transient blip must not abort it. **At least 3 attempts** per
provider with **increasing *deterministic* backoffs** (no jitter — this is a
startup gate, not load-shedding across workers; e.g. 2s, 4s, 6s). Only after
the attempts are exhausted does the run fail-fast.
  - Distinct from the mid-run retry policy (transient: 3 attempts, #2
  jittered; parse: 2 attempts). The preflight is deterministic and exists
  purely to distinguish "endpoint temporarily flaky" from "endpoint/auth
  genuinely broken" at startup.
- Auth/connectivity that dies **mid-run** still falls under the locked
"no circuit-breaker, all-`UNKNOWN`, user Ctrl-C" run-level stance.

## Open questions (next up)

- Input/output contract details: exact `results.csv` column order, encoding.
- Equality/normalization rules and the LLM-judge boundary (mostly locked).
- LLM contracts (JSON schemas, which model per role).
- Failure handling per stage (fail-fast vs continue) + the retry/backoff item
above.
- Security/credentials (Azure `DefaultAzureCredential`, Claude CLI auth).
- Scope boundaries; open risks / deferred; ADRs at close.
