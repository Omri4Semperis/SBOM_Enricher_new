# P4: license_download

**Your workspace.** This doc is writable. The other file you may edit is
`PLAN.md` — your table row, a concise Phase-notes reflection, and **Incoming
comments** in another phase's block. Never edit another phase's `P*` doc.

**Demo:** with HTTP mocked, a `github.com/.../blob/...` URL is rewritten to
`raw.githubusercontent.com`, the file is saved under `licenses/` and
`per_component/{slug}/`, and `inferred_license_code_url` becomes the URL that
actually worked.

**Goal:** Turn Claude's candidate URL into a real downloaded LICENSE file:
rewrite viewer URLs to raw, reject HTML/template responses, and on failure fall
back to purl-derived npm/unpkg candidates. Record the resolved URL and every
attempt.

## Entry criteria

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P3 Status is `done`
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed
- [ ] `git status --porcelain` → empty

## Context capsule

- P3 set `inferred_license_code_url` to Claude's raw candidate. P4 replaces it
  with the URL that actually downloaded, and saves the file. Confirm the result
  object field names in P2/P3 Phase-notes.
- `requests` is installed — use it (sync). Downloads run inside the per-
  component worker; if the pool is `asyncio`, wrap the sync download in a thread
  (`asyncio.to_thread`) so it doesn't block the loop. Keep it simple.
- Locked download rules (DECISIONS "License-file download"):
  - **Always rewrite viewer URLs to raw:** `github.com/<o>/<r>/blob/<ref>/<p>`
    → `raw.githubusercontent.com/<o>/<r>/<ref>/<p>`; GitLab `/-/blob/` →
    `/-/raw/`. Old `knowledge/old_code/src/license_fetcher.py`
    `_rewrite_viewer_url_to_raw` is the reference — adapt, don't import.
  - **Reject HTML / generic-template responses** (don't save site chrome as
    license text). Old `_looks_like_html_document` +
    `_is_generic_license_template_url` show the checks.
  - **On failure, fall back to purl-derived npm/unpkg candidates**
    (`LICENSE`, `LICENSE.md`, …). Old `_parse_npm_purl` /
    `_iter_npm_license_candidate_urls` show URL construction. npm/unpkg **only**
    (other ecosystems rely on Claude — broadening is BACKLOG #2, out of scope).
  - Empty purl → skip the npm fallback (nothing to derive); Story notes it.
  - `inferred_license_code_url` = the resolved URL that worked (not a dead one).
    The original Claude URL + every attempted source are preserved for the
    extended CSV (P8) — store them on the result object now.
  - No file saved → download failed closed; `inferred_license_code_url` may
    stay the last attempted or empty per your Story, copyright will be `UNKNOWN`
    (P5). Only that component affected (continue policy).
- Locked layout (P2): save to `licenses/{slug}.<ext>` (flat) and a copy in
  `per_component/{slug}/`. Extension from content/URL (old `license_filename` /
  `_decode_extensionless_text` are references).
- Reuse P3's `with_retries` for the transient HTTP retries (429/5xx/timeouts);
  hard 4xx (404) is not retried — fall back to the next candidate instead.

## Files

**Touch (complete list):**

- `src/download.py` — create: `fetch_license_file(claude_url, purl, dest_dir,
  slug) -> DownloadResult` (resolved URL + saved path + attempt list, or a
  failure result). Includes viewer→raw rewrite, HTML/template reject, npm/unpkg
  candidate generation.
- `src/pipeline.py` — edit: after license inference, call `fetch_license_file`;
  set the resolved `inferred_license_code_url`, saved-file path, and attempt log
  on the result object; append to Story.
- `tests/test_download.py` — create: mock `requests`; assert rewrite, HTML
  reject, npm fallback ordering, resolved-URL selection, file written to both
  locations, empty-purl skips fallback.

**Do not touch:** `claude_client.py`, copyright/cache/audit code, `knowledge/`.

## Tasks

### T1: URL rewrite + reject + candidates (pure funcs)

- Steps: in `src/download.py`, pure helpers: `rewrite_viewer_to_raw(url)`,
  `looks_like_html(body, content_type)`, `is_generic_template(url)`,
  `npm_candidates(purl) -> list[str]`.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_download.py -k
  "rewrite or html or candidates"` → exit 0.
- Commit when green.

### T2: fetch orchestration

- Steps: `fetch_license_file` — try Claude URL (rewritten) via `with_retries`,
  reject HTML/template, on failure iterate npm/unpkg candidates; on first good
  body write `licenses/{slug}.<ext>` + copy into `per_component/{slug}/`, return
  resolved URL + path + attempts.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_download.py` →
  exit 0 (mock `requests`: blob URL → raw fetched + saved; bad Claude URL →
  npm fallback succeeds; all fail → failure result, no file).
- Commit when green.

### T3: wire into pipeline

- Steps: `src/pipeline.py` — call `fetch_license_file`, update the result
  object (resolved URL, saved path, attempts), Story lines for each attempt +
  why chosen.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_pipeline.py` →
  exit 0 (mock inference + download; assert resolved URL in results CSV, file
  path recorded).
- Commit when green.

## Validation gate

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. Fresh review of `git diff {baseline}..HEAD` by a `generalPurpose` readonly
   subagent (diff + this doc + over-engineering lens). Fix findings, re-run 1;
   ordered-behavior findings recorded not fixed.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- Test proving blob→raw rewrite + save + resolved-URL selection passes.

## Rollback

`git reset --hard {baseline hash from PLAN.md}`, Status `blocked` + one-line
reason in Phase-notes.

## Failure modes

1. Real network in tests → always mock `requests`; no live downloads in suite.
2. Saving HTML as "license text" → the HTML/template reject must run before any
   write; test it explicitly.
3. Broadening fallback past npm/unpkg → out of scope (BACKLOG #2); npm/unpkg
   only.

## Anti-goals

- No copyright extraction (P5), no cache (P6), no audit (P7).
- No PyPI/Maven/Cargo fallbacks — BACKLOG #2.
- No npm-author copyright fallback (old `fetch_npm_author`) — dropped in v2
  (ADR 0003 / BACKLOG #4).
- Nothing beyond this doc's Tasks.

## If blocked

Set Status `blocked` in `PLAN.md` (Baseline + Updated), one-line reason in
Phase-notes, report and stop.

## On completion

1. Re-check Entry/Validation/Exit.
2. `PLAN.md`: Status `done`, Baseline + Updated.
3. Reflect into Phase-notes: `fetch_license_file` signature + `DownloadResult`
   shape (saved path field is what P5/P6 consume), where attempts are stored
   for P8's extended CSV.
4. Record full **Outcome** here (same shape as P1's).

## Outcome

Objective: license-file download with viewer→raw, HTML/template reject, npm/unpkg fallback
HEAD: 1ecced6 | Branch: master
Files changed:
- docs/plans/v2-enricher/PLAN.md
- docs/plans/v2-enricher/P4_license_download.md
- src/download.py
- src/pipeline.py
- tests/test_download.py
- tests/test_pipeline.py
Commands run:
- Entry: `pytest -q` → 26 passed; porcelain empty; baseline `f7b3f36`
- T1: `pytest -q tests/test_download.py -k "rewrite or html or candidates"` → 9 passed
- T2: `pytest -q tests/test_download.py` → 16 passed
- T3: `pytest -q tests/test_pipeline.py` → 3 passed
- Gate: `pytest -q` → 43 passed; review PASS; post-shrink `pytest -q` → 43 passed
Test status: `.\.venv\Scripts\python.exe -m pytest -q` → 43 passed
Assumptions: extensionless LICENSE URLs save as `{slug}.txt`; download failure keeps Claude's candidate URL on `inferred_license_code_url`
Open questions: none
Next action: P5 (copyright_extraction)
