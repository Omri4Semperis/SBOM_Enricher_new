# P2: nuget_nuspec_fallback

**Plan:** fact-grade-first tranche — make the audit measurement truthful without
gaming the headline number. This phase is the one genuine agent-recall win; read
`PLAN.md`'s Goal and Context in full before starting.

**Your workspace.** This doc is writable: record decisions, dead ends, and
findings here during implementation. The other file you may edit is `PLAN.md`
(your table row, your Phase-notes block, and Incoming comments in other blocks).
Never edit another phase's `P*` doc. Status lives in `PLAN.md`'s table.

**Demo:** for a `pkg:nuget/...` purl whose nuspec declares a `<repository url>`,
`fetch_license_file` downloads a real LICENSE file from that repo's raw host —
shown by `pytest tests/test_download.py -k nuget -q` (network mocked).

**Goal:** Give NuGet packages a downloadable LICENSE-file fallback, mirroring the
npm path. Add `nuget_candidates(purl)` that reads the package nuspec, and when it
declares a source `<repository url>`, derive raw LICENSE candidate URLs from that
repo (reusing `NPM_LICENSE_FILENAMES`) so `fetch_license_file` can download the
real file. When the nuspec only carries an SPDX expression or a legacy EULA
`licenseUrl`, produce **no** candidate — never invent a URL — so the URL field
stays empty and P1's blank→Unknown grades it `Unknown`.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0 (`119 passed`, or higher if P1 already merged — either is fine; P2 has no dependency)
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

`src/download.py` today:
- `npm_candidates(purl) -> list[str]` is the shape to mirror: it parses a
  `pkg:npm/...` purl into `name@version` and returns unpkg URLs, one per entry in
  `NPM_LICENSE_FILENAMES` (a module-level tuple of LICENSE/COPYING/NOTICE names).
- `fetch_license_file(claude_url, purl, dest_dir, slug)`: tries the claude URL via
  `_try_one`, then loops `npm_candidates(purl)`. It logs a skip line when the purl
  is empty or non-npm. `_try_one` already rewrites viewer→raw, rejects HTML, and
  writes the file — reuse it for nuget candidates unchanged.
- `rewrite_viewer_to_raw(url)` handles github.com `/blob/` and gitlab `/-/blob/`.
  NuGet repo URLs are often `https://github.com/{owner}/{repo}` with no ref; you
  must build raw candidate URLs yourself (see below), not rely on the rewriter.
- HTTP fetch helper: `requests` is imported as `download.requests`; tests
  monkeypatch `download.requests.get`. There is a `FETCH_TIMEOUT_S = 30.0`.

nuspec facts (for `nuget_candidates`):
- Flat-container nuspec URL:
  `https://api.nuget.org/v3-flatcontainer/{id_lower}/{version}/{id_lower}.nuspec`
  where `{id_lower}` is the lowercased package id.
- The nuspec is XML with a default namespace; `<repository url="..." />` and
  `<license type="expression|file">...</license>` / legacy `<licenseUrl>` live
  under `<metadata>`. Parse with `xml.etree.ElementTree` and match tags by local
  name (ignore the namespace) — e.g. iterate elements and compare
  `tag.rsplit('}', 1)[-1]`.
- From a `<repository url>` like `https://github.com/foo/bar` (strip a trailing
  `.git`), build raw candidates:
  `https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{filename}` for each
  `filename` in `NPM_LICENSE_FILENAMES`. (HEAD is acceptable — see Anti-goals /
  the accepted version-skew risk in DECISIONS branch I #2.)

DECISIONS branch E is the spec. Boundary: the nuspec's SPDX id may inform the
license **name** field elsewhere, but this function's only job is the **URL**
field's downloadable file — it must never fabricate a URL from an SPDX id.

## Files

**Touch (complete list):**

- `src/download.py` — edit: add `nuget_candidates(purl)` and call it inside
  `fetch_license_file` as a fallback after (or alongside) the npm candidates.
- `tests/test_download.py` — edit: unit-test nuspec parsing + the fetch wiring.

**Do not touch:** `src/copyright.py`'s `_npm_package_name` (separate concern),
`src/prompts.py` (the SPDX-id→name side is out of scope), and anything not listed
above. Needing an unlisted file means the plan is wrong: record it here and in
your `PLAN.md` block; if you can't proceed, follow **If blocked**.

## Tasks

### T1: Add `nuget_candidates(purl)`

- Steps:
  - Parse `pkg:nuget/{id}@{version}` (return `[]` for non-nuget or missing
    version). Lowercase the id for the flat-container path.
  - Fetch the nuspec via `requests.get(nuspec_url, timeout=FETCH_TIMEOUT_S)`;
    on any non-200 or exception return `[]` (fail closed — the fallback is a
    best-effort bonus, never a crash).
  - Parse XML by local tag name. If `<repository url>` present, derive raw
    candidates from it (strip trailing `.git`; `.../{owner}/{repo}/HEAD/{filename}`
    for each `NPM_LICENSE_FILENAMES`). Otherwise return `[]` (SPDX-only or legacy
    `licenseUrl` → no fetchable file → empty).
- Verify: add `test_nuget_candidates_repo` (mock `download.requests.get` to return
  a nuspec XML string with a `<repository url>` → first candidate is the raw
  `.../HEAD/LICENSE` URL) and `test_nuget_candidates_spdx_only_empty` (nuspec with
  only `<license type="expression">MIT</license>` → `[]`), and
  `test_nuget_candidates_non_nuget` (`npm`/empty purl → `[]`).
  `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -k nuget -q` → exit 0.
- Commit when green.

### T2: Wire `nuget_candidates` into `fetch_license_file`

- Steps: after the npm-candidate loop fails (or before `result.error =
  "download_failed"`), if the purl is `pkg:nuget/...`, loop `nuget_candidates(purl)`
  through `_try_one` exactly like the npm loop; on success set `resolved_url`
  (`rewrite_viewer_to_raw(candidate)`) and `saved_path` and return. Add an
  attempts skip line for non-nuget purls consistent with the existing npm skip
  logging.
- Verify: add `test_fetch_nuget_fallback_after_bad_claude` — claude URL 404s, the
  nuspec fetch returns a `<repository url>`, and the raw LICENSE URL returns a
  200 license body; assert `result.ok`, `resolved_url` is the raw LICENSE URL, and
  the file was written. Mock `download.requests.get` to route by URL.
  `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q` → exit 0.
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, baseline `+ new tests` passed
2. Fresh review: the diff `git diff <baseline>..HEAD` (baseline = the hash you
   recorded in `PLAN.md` at phase start) reviewed against this doc plus an
   over-engineering lens by a context that did not implement it (subagent given
   only the diff, this doc, and the lens; if subagents are unavailable, stop and
   ask the user to review in a new session). Fix findings, re-run 1 — but a lens
   finding on something this doc explicitly ordered is NOT fixed; record it here.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -k nuget -q` → exit 0, ≥3 passed
- `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q` → exit 0 (npm path unbroken)

## Rollback

To abandon this phase: `git reset --hard <baseline hash from PLAN.md's phase table>`,
then set this phase's Status to `blocked` in `PLAN.md` with a one-line reason in
your Phase-notes block.

## Failure modes

1. XML namespace makes `.find("repository")` return `None` → match by **local**
   tag name (`tag.rsplit('}', 1)[-1] == "repository"`), don't hard-code the
   namespace URI.
2. A NuGet package with no repo but an SPDX id starts producing a URL → that's a
   contract violation; `nuget_candidates` must return `[]` in that case, never a
   fabricated `licenses.nuget.org`/SPDX URL.
3. nuspec fetch hangs or errors on a bad id → the `except → []` guard must cover
   it so the run never crashes on the fallback.

## Anti-goals

Do not, even if it seems better:

- No SPDX-id→URL fabrication, ever (the core boundary of DECISIONS E).
- No version-pinning heuristics for the repo LICENSE — HEAD is the accepted
  shortcut (DECISIONS branch I risk #2). Mark it with a `ponytail:` comment
  (`# ponytail: HEAD ref, pin to tag if version skew bites`) and move on.
- No touching the license-**name** field or the SPDX-informs-name path.
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here" fixes.

## Outcome
Objective: Give NuGet packages a downloadable LICENSE-file fallback via nuspec
`<repository url>`, mirroring the npm path, without ever fabricating a URL
from an SPDX id.
HEAD: bce9ea6 | Branch: master
Files changed: src/download.py, tests/test_download.py
Commands run:
- `pytest tests/test_download.py -k nuget -q` → 4 passed (T1: 3, plus T2's
  wiring test also matches "nuget")
- `pytest tests/test_download.py -q` → 22 passed (npm path unbroken)
- `pytest -q` (full suite) → 126 passed (122 baseline + 4 new)
- Fresh-context subagent review (diff `453f143..HEAD` + this doc + ponytail-
  review tag lens): spec conformance PASS, failure-mode handling PASS,
  anti-goals PASS, over-engineering findings none ("Lean already. Ship.").
Assumptions:
1. Only GitHub-shaped `<repository url>` values produce a working raw URL
   (owner/repo path segments → `raw.githubusercontent.com`); a non-GitHub host
   still returns a candidate list but it will 404 harmlessly rather than
   short-circuiting to `[]`. This matches this doc's Context capsule (which
   only specifies the github.com raw-URL shape) but is narrower than
   DECISIONS.md branch E's "repo's raw host" phrasing — flagged in PLAN.md for
   a future phase if non-GitHub NuGet repos turn out to matter.
2. HEAD ref (not a pinned tag) is the accepted version-skew shortcut per
   DECISIONS branch I risk #2; marked with the required `ponytail:` comment.
Open questions: none.
Next action: P3 (copyright_honesty) — no dependency on P2, ready to run. P4
(offline_rescore_signoff) still blocked on P3.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (start hash)
   and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block.
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
