# P3: license_inference

**Your workspace.** This doc is writable: record whatever detail you need here.
The other file you may edit is `PLAN.md` — your table row, a concise reflection
in your Phase-notes block, and **Incoming comments** in another phase's block.
You never edit another phase's `P*` doc.

**Demo:** with the Claude call mocked, `process_component` on a fixture fills
`inferred_license_name` and `inferred_license_code_url` from the parsed JSON,
and the Story records the `reasoning`.

**Goal:** Add the real license-inference stage: a single Claude CLI call
returning `{license_name, license_code_url, reasoning}`, with the locked retry/
backoff policy, wired into the P2 pipeline replacing the license stub. Download
still stubbed; copyright still `UNKNOWN`.

## Entry criteria

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P2 Status is `done`
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed
- [ ] `git status --porcelain` → empty

## Context capsule

- P2 exposes the pipeline: result object, `process_component` signature, worker
  pool, Story-append helper, `model_short` — confirm the real names in P2's
  Phase-notes block.
- Claude call shape (from `knowledge/query_example_claude.py`, adapt — do not
  import): subprocess `claude -p <prompt> --model <model> --allowedTools
  WebSearch,WebFetch --output-format json [--json-schema <schema>]`, `cwd =
  Path.home()`, async via `asyncio.create_subprocess_exec`. Non-zero exit →
  transient failure. Parse: `json.loads(stdout)`, prefer `structured_output`,
  else `result`. Old `knowledge/old_code/src/client.py` shows the same idea
  with more layers — take the shape, not the structure.
- Locked contract (DECISIONS "LLM contract — license inference"): exactly
  three fields, all always present:

```json
{
  "license_name": "<SPDX id / shorthand, or UNKNOWN>",
  "license_code_url": "<raw downloadable LICENSE URL, or empty string>",
  "reasoning": "<concise sources-checked summary>"
}
```

  `license_name = "UNKNOWN"` is the couldn't-determine signal. No `confidence`.
  Map 1:1 to `inferred_license_name` / `inferred_license_code_url`.
- Locked inputs ("Identifiers & parsing"): `purl` is the primary identifier in
  the prompt; `lib_name`/`version` are secondary human context. Empty purl →
  still call Claude with lib/version context (degraded), Story notes "no purl".
- Locked prompt policy ("Prompting"): take **inspiration** from
  `knowledge/old_code/src/config.py` `build_query_prompt` (anti-template rules,
  raw-URL preference, lookup hierarchy) — rewrite for the new field names, do
  not paste. Prompt lives in v2 source (e.g. `src/prompts.py`).
- Locked retry/backoff ("Retry / backoff policy") — hard-coded constants, not
  config:
  - Transient (network/timeout/HTTP 429 or 5xx/CLI non-zero exit): 3 attempts
    total. Retry #1 after fixed **2s** `asyncio.sleep`; retry #2 after uniform
    random in **[3s, 8s]**. Hard 4xx (401/403/404) → not retried, fail stage.
  - Parse failure (responded but not the requested JSON): 2 attempts total;
    retry after fixed **1s** (no jitter).
  - After retries exhaust → stage fails closed: `inferred_license_name =
    UNKNOWN`, reason in Story + (later) extended CSV; only that component
    affected (continue policy).
- Put the retry helper in `src/retry.py` (a small async wrapper taking a
  callable, the two attempt counts, and a classifier for transient vs parse vs
  hard) — P5's copyright call reuses it, so keep it generic but tiny.

## Files

**Touch (complete list):**

- `src/claude_client.py` — create: async `infer_license(purl, lib_name,
  version, model) -> dict` (the CLI call + JSON parse + contract validation).
- `src/prompts.py` — create: `license_prompt(...)` returning the prompt string
  (+ the JSON schema passed to `--json-schema`).
- `src/retry.py` — create: generic async retry wrapper with the locked
  constants + failure classification.
- `src/pipeline.py` — edit: replace the license stub with a call to
  `infer_license`, set the two inferred fields, append reasoning to the Story.
- `tests/test_claude_client.py`, `tests/test_retry.py` — create: mock the
  subprocess; assert contract parse, `UNKNOWN` on exhausted retries, transient
  vs parse attempt counts, hard-4xx no-retry.

**Do not touch:** download logic (P4), copyright (P5), `results_csv.py` column
set, `knowledge/`.

## Tasks

### T1: retry wrapper

- Steps: `src/retry.py` — async `with_retries(fn, *, transient_attempts=3,
  parse_attempts=2, classify)` sleeping 2s then uniform[3,8] for transient, 1s
  for parse; re-raises hard failures immediately.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_retry.py` → exit
  0 (fake fn raising each failure kind; assert attempt counts, patch
  `asyncio.sleep` to not really wait).
- Commit when green.

### T2: Claude client + prompt

- Steps: `src/prompts.py` `license_prompt` + schema; `src/claude_client.py`
  `infer_license` doing the subprocess call through `with_retries`, parsing the
  three-field contract, returning `UNKNOWN`/empty-url on failure.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_claude_client.py`
  → exit 0 (mock `create_subprocess_exec`: valid JSON → parsed dict; garbage →
  `UNKNOWN` after parse retries; non-zero exit → transient retries then
  `UNKNOWN`).
- Commit when green.

### T3: wire into pipeline

- Steps: `src/pipeline.py` — call `infer_license` in `process_component`, set
  `inferred_license_name` / `inferred_license_code_url`, append `reasoning` +
  attempts + timing to the Story.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_pipeline.py` →
  exit 0 (mock `infer_license`; assert results CSV shows the mocked name/url,
  Story mentions the reasoning).
- Commit when green.

## Validation gate

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. Fresh review of `git diff {baseline}..HEAD` by a `generalPurpose` readonly
   subagent (diff + this doc + over-engineering lens only). Fix findings,
   re-run 1; ordered-behavior findings recorded not fixed.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- Test proving a mocked valid Claude response lands in the results CSV columns
  passes (part of the suite).

## Rollback

`git reset --hard {baseline hash from PLAN.md}`, Status `blocked` + one-line
reason in Phase-notes.

## Failure modes

1. Real `claude` CLI invoked in tests → always mock the subprocess; no live
   calls in the suite.
2. Retry sleeps make tests slow → patch `asyncio.sleep`.
3. Over-generalizing the retry wrapper (backoff strategies, config) → keep it
   to the two locked policies; P5 reuses it as-is.

## Anti-goals

- No download / no viewer→raw rewrite — P4 owns it (Claude's URL is stored
  as-is for now; P4 resolves it).
- No copyright, no cache, no audit, no consistency judge (dropped in v2).
- No cost/token capture yet — P8.
- Nothing beyond this doc's Tasks.

## If blocked

Set Status `blocked` in `PLAN.md` (Baseline + Updated), one-line reason in
Phase-notes, report and stop.

## On completion

1. Re-check Entry/Validation/Exit.
2. `PLAN.md`: Status `done`, Baseline + Updated.
3. Reflect into Phase-notes: final `infer_license` signature/return, the
   `with_retries` signature (P5 reuses it), where prompts live.
4. Record full **Outcome** here (same shape as P1's).
