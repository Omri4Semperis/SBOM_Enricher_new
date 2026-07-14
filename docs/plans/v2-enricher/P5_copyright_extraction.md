# P5: copyright_extraction

**Your workspace.** This doc is writable. The other file you may edit is
`PLAN.md` — your table row, a concise Phase-notes reflection, and **Incoming
comments** in another phase's block. Never edit another phase's `P*` doc.

**Demo:** with GPT-4.1 mocked, a component whose LICENSE file was downloaded
gets a verbatim `inferred_copyright`; a component with no file gets `UNKNOWN`
without any LLM call.

**Goal:** Add file-only copyright extraction (ADR 0003): a fixed GPT-4.1 call
reads the downloaded LICENSE text and returns `{copyright, reasoning}`. No file
⇒ `UNKNOWN`, no fallbacks. The GPT-4.1 client built here is reused by P7's
equality judge, so make it a small reusable class.

## Entry criteria

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments**
- [ ] P4 Status is `done`
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed
- [ ] `git status --porcelain` → empty

## Context capsule

- P4 saved the LICENSE file and recorded its path on the result object. P5
  reads ONLY that file. No file → `inferred_copyright = UNKNOWN`, no call.
- GPT-4.1 call shape (from `knowledge/query_example_gpt-4-1.py`, adapt — do not
  import): `AsyncAzureOpenAI` with `azure_ad_token_provider =
  get_bearer_token_provider(DefaultAzureCredential(), AZURE_TOKEN_SCOPE)`.
  Fixed non-secret constants (locked "Security / credentials", "Model: fixed vs
  configurable"):
  - `AZURE_ENDPOINT = "https://ai-foundry-rnd-dev.cognitiveservices.azure.com/"`
  - `GPT41_DEPLOYMENT = "gpt-4.1-limitless"`
  - `AZURE_API_VERSION = "2024-12-01-preview"`
  - `AZURE_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"`

  These live in source, NOT `default.json`. No API-key path (ambient credential
  only). Never write tokens to Stories/CSVs/summary.
- Locked contract (DECISIONS "LLM contract — copyright extraction"): input is
  the LICENSE file **text only**; output:

```json
{ "copyright": "<verbatim statement, or UNKNOWN>", "reasoning": "<one sentence>" }
```

  Value is the full statement as it appears, trimmed (e.g.
  `Copyright (c) 2020 Jane Doe`), not just the holder. `UNKNOWN` sentinel
  replaces a `found` boolean. Maps to `inferred_copyright`.
- Locked no-fallbacks (ADR 0003): no npm-author, no Claude web copyright. File
  missing or no real holder ⇒ `UNKNOWN`. (Fallbacks are BACKLOG #4.)
- Locked prompt policy ("Prompting"): inspiration from
  `knowledge/old_code/src/config.py` `build_copyright_query_prompt` and
  `knowledge/old_code/src/copyright_extractor.py` (e.g. placeholder-copyright
  detection) — rewrite, don't paste. Prompt goes in `src/prompts.py`.
- Reuse P3's `src/retry.py` `with_retries` for the transient/parse policy
  (same locked constants). The GPT-4.1 client class should expose a generic
  "call with system+user prompt, parse JSON" method so P7 reuses it for the
  judge.

## Files

**Touch (complete list):**

- `src/gpt41_client.py` — create: reusable `Gpt41Client` (async chat call with
  the fixed deployment via `DefaultAzureCredential`, JSON parse, retry).
- `src/copyright.py` — create: `extract_copyright(license_text) -> dict`
  ({copyright, reasoning}) using `Gpt41Client`.
- `src/prompts.py` — edit: add `copyright_prompt(...)` (system + user).
- `src/pipeline.py` — edit: after download, if a file exists call
  `extract_copyright(file_text)`, set `inferred_copyright`, Story lines; else
  `UNKNOWN`.
- `tests/test_copyright.py` — create: mock `Gpt41Client`; verbatim copyright on
  a fixture LICENSE, `UNKNOWN` when no file, `UNKNOWN` after parse retries.

**Do not touch:** cache (P6), audit/equality (P7 — though it reuses
`Gpt41Client`, that class is finalized here), `knowledge/`.

## Tasks

### T1: GPT-4.1 client

- Steps: `src/gpt41_client.py` `Gpt41Client` with an async
  `complete_json(system_prompt, user_prompt) -> dict` that calls the fixed
  deployment through `with_retries`, parses JSON, raises a parse failure the
  wrapper can classify.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_copyright.py -k
  client` → exit 0 (mock `AsyncAzureOpenAI`; valid JSON → dict; garbage →
  parse-retry then error). No live Azure calls.
- Commit when green.

### T2: copyright extraction

- Steps: `src/prompts.py` `copyright_prompt`; `src/copyright.py`
  `extract_copyright(license_text)` → `{copyright, reasoning}`, returning
  `UNKNOWN` on failure/placeholder.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_copyright.py -k
  extract` → exit 0 (fixture LICENSE text → verbatim; placeholder → `UNKNOWN`).
- Commit when green.

### T3: wire into pipeline

- Steps: `src/pipeline.py` — call `extract_copyright` only when a file path is
  present; set `inferred_copyright`; Story lines; no file → `UNKNOWN`, no call.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q tests/test_pipeline.py` →
  exit 0 (mock inference+download+copyright; file present → verbatim in results
  CSV; no file → `UNKNOWN`, extractor not called).
- Commit when green.

## Validation gate

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
2. Fresh review of `git diff {baseline}..HEAD` by a `generalPurpose` readonly
   subagent (diff + this doc + over-engineering lens). Fix findings, re-run 1;
   ordered-behavior findings recorded not fixed.

## Exit criteria

- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, all passed.
- Test proving "no downloaded file ⇒ `UNKNOWN`, extractor not called" passes.

## Rollback

`git reset --hard {baseline hash from PLAN.md}`, Status `blocked` + one-line
reason in Phase-notes.

## Failure modes

1. Live Azure token/call in tests → mock `AsyncAzureOpenAI` and the credential;
   no network in the suite.
2. Adding a fallback when the file yields nothing → forbidden (ADR 0003);
   `UNKNOWN` is the answer.
3. Leaking a token into Story/CSV → never log credentials or raw auth headers.

## Anti-goals

- No npm-author / Claude-web copyright fallback — ADR 0003, BACKLOG #4.
- No cache (P6), no audit/equality judge behavior (P7) — but `Gpt41Client` is
  finalized here for P7 to reuse.
- No cost capture yet — P8.
- Nothing beyond this doc's Tasks.

## If blocked

Set Status `blocked` in `PLAN.md` (Baseline + Updated), one-line reason in
Phase-notes, report and stop.

## On completion

1. Re-check Entry/Validation/Exit.
2. `PLAN.md`: Status `done`, Baseline + Updated.
3. Reflect into Phase-notes: `Gpt41Client.complete_json` signature (P7 reuses
   it), `extract_copyright` signature, the fixed Azure constants' location.
4. Record full **Outcome** here (same shape as P1's).
