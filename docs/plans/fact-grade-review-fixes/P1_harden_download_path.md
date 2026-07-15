# P1: harden_download_path

**Plan:** fact-grade-review-fixes — clear every review finding so the
fact-grade tranche signs off. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** Write freely here during implementation. Your only other
editable file is `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other phases' blocks); never another phase's `P*` doc.

**Demo:** `pytest tests/test_download.py -q` is green with four new tests: a
non-GitHub nuspec repo yields no candidates, an uppercase prerelease version
normalizes, the nuspec fetch is offloaded off the loop, and a NuGet lookup
that finds nothing logs a NuGet-specific message.

**Goal:** Fix the four `src/download.py` findings (B1 blocker, S2/S3
should-fixes, N1 nit) in one pass, since they all touch the same file and its
test file. Record the B1 fail-closed host policy as ADR 0008.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] No dependencies to check (this phase depends on nothing)
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, 130 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

`src/download.py` — license-file download. Key facts for this phase:

- `nuget_candidates(purl: str) -> list[str]` (line ~114) builds unpkg-style
  raw LICENSE URLs from a `pkg:nuget/` purl's nuspec `<repository url>`. It is
  **fail-closed**: any network/parse issue or a nuspec without a usable
  `<repository url>` returns `[]`, never a fabricated URL. Flow: parse purl →
  build `nuspec_url` on `api.nuget.org/v3-flatcontainer/{id}/{version}/{id}.nuspec`
  → `requests.get` → parse XML → read first `<repository url>` → strip `.git` →
  take first two path segments as `owner`, `repo` → emit
  `raw.githubusercontent.com/{owner}/{repo}/HEAD/{filename}` for each
  `NPM_LICENSE_FILENAMES`.
  - **B1 bug (line ~159):** the `owner/repo` is taken from *any* host's URL, so
    a nuspec pointing at `gitlab.com/foo/bar` or `example.com/a/b` becomes a
    `raw.githubusercontent.com/a/b/...` URL — misattribution if that repo
    exists on GitHub.
  - **S3 bug (line ~132–138):** `version` is used verbatim in `nuspec_url`. The
    flat-container endpoint requires a NuGet-normalized, lowercased version.
- `rewrite_viewer_to_raw` already recognizes GitHub hosts as
  `{"github.com", "www.github.com"}` — reuse that exact set for B1.
- `fetch_license_file` (async, line ~273) calls `nuget_candidates(purl)`
  **synchronously** at line ~317 inside the asyncio worker — S2 bug. Compare
  `_npm_author_copyright` in `src/copyright.py`, called via
  `await asyncio.to_thread(...)`; do the same here. `npm_candidates` is pure
  string work and is NOT offloaded — only `nuget_candidates` does HTTP.
- **N1 bug (line ~321):** when `nuget_cands` is empty, the code logs
  `"non-nuget purl: skip nuget fallback"` even for a real `pkg:nuget/` purl
  whose lookup failed.

Tests: `tests/test_download.py` uses `monkeypatch.setattr("download.requests.get", fake_get)`
to fake HTTP. Existing NuGet tests to mirror: `test_nuget_candidates_repo`,
`test_nuget_candidates_spdx_only_empty`, `test_nuget_candidates_non_nuget`,
`test_fetch_nuget_fallback_after_bad_claude`. Async fetch tests use
`asyncio.run(...)`.

NuGet version normalization rule (S3): URL-decode, strip SemVer build
metadata (everything from a `+`), lowercase, strip leading zeros per numeric
segment, and drop a zero-valued 4th segment (`1.0.0.0` → `1.0.0`). Examples:
`1.0.0.0` → `1.0.0`; `1.02.3` → `1.2.3`; `1.0.0+build.5` → `1.0.0`;
`2.1.0-RC1` → `2.1.0-rc1`.

## Files

**Touch (complete list):**

- `src/download.py` — edit: B1 host gate + S3 version normalizer in
  `nuget_candidates`; S2 `to_thread` offload + N1 log branch in
  `fetch_license_file`.
- `tests/test_download.py` — edit: add four tests (one per finding).
- `docs/adr/0008-nuget-repo-github-host-gate.md` — create: record the B1
  fail-closed policy.

**Do not touch:** `src/copyright.py` (P2 owns it),
`ad_hoc_scripts/analysis/rescore.py` (P3 owns it), and anything not listed
under Touch. Needing an unlisted file means the plan is wrong: record it as a
note in this doc and a comment in your `PLAN.md` block; if the phase can't
proceed without it, follow **If blocked**.

## Tasks

### T1: B1 — gate raw-URL construction on a recognized GitHub host

- Steps: In `nuget_candidates`, after resolving `owner, repo` from the nuspec
  `<repository url>`, add a host check: parse the repo URL host with
  `urlsplit(repo_url).hostname` lowercased; if it is not in
  `{"github.com", "www.github.com"}`, `return []`. Keep the existing
  `len(segments) < 2` guard. Do not implement other hosts' raw-URL forms —
  fail closed (that decision is ADR 0008, T5).
- Add test `test_nuget_candidates_non_github_repo_empty(monkeypatch)`: fake the
  nuspec fetch to return a nuspec whose `<repository url>` is
  `https://gitlab.com/someowner/somerepo.git`; assert `nuget_candidates(...)`
  returns `[]` (the collision test the review asked for).
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q` → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: S3 — normalize the NuGet version before building the nuspec URL

- Steps: Add a small helper `_normalize_nuget_version(version: str) -> str` in
  `download.py` applying the rule in the capsule (URL-decode, strip `+...`
  build metadata, lowercase, strip per-segment leading zeros, drop a
  zero-valued 4th segment). Call it in `nuget_candidates` where `version` is
  currently used verbatim to build `nuspec_url`. The `@`-split still uses the
  raw remainder; normalize only the value that goes into the URL.
- Add test `test_nuget_version_normalized(monkeypatch)`: capture the URL
  `requests.get` is called with for
  `pkg:nuget/Some.Package@1.0.0.0` (or an uppercase prerelease like
  `2.1.0-RC1`) and assert the nuspec URL contains the normalized, lowercased
  version (`.../1.0.0/...` or `.../2.1.0-rc1/...`).
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q` → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T3: S2 — offload the synchronous nuspec fetch off the event loop

- Steps: In `fetch_license_file`, change `nuget_cands = nuget_candidates(purl)`
  (line ~317) to `nuget_cands = await asyncio.to_thread(nuget_candidates, purl)`.
  `asyncio` is already imported.
- Add test `test_fetch_nuget_offloaded_from_loop(tmp_path, monkeypatch)`: make
  `nuget_candidates` block briefly (monkeypatch `download.requests.get` to
  `time.sleep` then return a valid nuspec) and assert that
  `fetch_license_file` does not block the running loop — e.g. run two
  `fetch_license_file` calls concurrently with `asyncio.gather` and assert
  wall-clock time is less than the serial sum, OR assert the call is dispatched
  via `asyncio.to_thread` by monkeypatching it and checking it was awaited.
  Prefer the simpler of the two that reliably passes; the point is a
  regression guard that the fetch is no longer inline.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q` → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T4: N1 — distinguish a non-NuGet purl from a failed NuGet lookup

- Steps: In `fetch_license_file`, the branch at line ~318–321 that appends
  `"non-nuget purl: skip nuget fallback"` when `nuget_cands` is empty must
  split: if `(purl or "").strip().lower().startswith("pkg:nuget/")`, append
  `"nuget: no candidates (nuspec/repo lookup failed)"`; else keep the existing
  `"non-nuget purl: skip nuget fallback"`. Leave the empty-purl branch as is.
- Add test `test_fetch_nuget_purl_no_candidates_logs_lookup_failure(tmp_path, monkeypatch)`:
  make `nuget_candidates` return `[]` for a `pkg:nuget/...` purl (fake the
  nuspec fetch to a non-200 or a nuspec without a GitHub repo) and no Claude
  URL; assert the resulting `DownloadResult.attempts` contains
  `"nuget: no candidates (nuspec/repo lookup failed)"` and NOT
  `"non-nuget purl"`.
- Verify: `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q` → exit 0, all passed.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T5: ADR 0008 — record the B1 fail-closed host policy

- Steps: Create `docs/adr/0008-nuget-repo-github-host-gate.md` following the
  house style of `docs/adr/0006-unscoreable-grade.md` (a `status: accepted`
  front-matter, a decision title, a short body, a **Rejected:** list). Decision:
  *never derive a `raw.githubusercontent.com` URL from a nuspec `<repository
  url>` unless the repo host is a recognized GitHub host* — because reducing an
  arbitrary host's `owner/repo` to a GitHub raw URL can silently attribute an
  unrelated GitHub repository's license. Rejected alternatives: (a) implement
  each other host's real raw-URL form (rots, and each host is a new
  attack surface for the same collision), (b) trust the `owner/repo` regardless
  of host (the bug). Keep it under ~40 lines.
- Verify: `.\.venv\Scripts\python.exe -m py_compile src/download.py` → exit 0
  (sanity), and the file exists with the front-matter.
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥134 passed (130
   baseline + 4 new tests).
2. No typecheck/lint tool is configured in this repo; skip.
3. Fresh review: the diff `git diff {baseline}..HEAD` (substitute the hash
   recorded in `PLAN.md` at phase start) is reviewed against this doc plus an
   over-engineering lens by a context that did not implement it (subagent given
   only the diff, this doc, and the lens; if subagents are unavailable, stop and
   ask the user to review in a new session). Fix findings, re-run 1. A lens
   finding on something this doc explicitly ordered (e.g. the ADR, or the
   fail-closed policy) is NOT fixed; record it as a note here.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q` → exit 0, all passed (includes the 4 new tests).
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥134 passed.

## Anti-goals

Do not, even if it seems better:

- No refactor of `fetch_license_file`'s fallback ordering or the npm path — the
  four fixes are surgical.
- Do not implement non-GitHub hosts' raw-URL forms (that is the rejected
  alternative in ADR 0008).
- Do not touch `_is_stray_holder` or `rescore.py` — P2/P3 own those.

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
   — confirm `nuget_candidates`'s signature is unchanged (P3 is unaffected).
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
