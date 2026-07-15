# HANDOFF — accuracy levers, deferred until a corrected-input run exists

## Focus

User directive (verbatim): "the input file of this run wasn't accurate —
contains mistakes of licenses. You can build what it takes to speed up the
process, and fix the Terminology — but DO NOT do anything meant to fix
accuracy. Once this is done, I'll re-run on an actually accurate file to
assert we have true results to improve upon."

- Objective: hold all accuracy work until Omri re-runs on a corrected input
  file; then execute the accuracy levers below against a trustworthy baseline.
- Repo: C:\Users\OmriNardiNiri\Documents\_Dev\2026-06-07 improve sbom-enricher agent\SBOM_Enricher_new
- Branch: master
- HEAD: 945409e
- Dirty: working tree was clean at HEAD; this session edited `docs/CONTEXT.md`
  and added this file (`docs/HANDOFF.md`). No code changed.

## Why accuracy is on hold

The scored run `20260715_013034_ClaudeOpu-4-8_380` used an input whose
ground-truth license columns contain mistakes. `score.csv` (Hit/Mismatch/
Unknown) is therefore untrustworthy — Mismatches may be GT errors, not model
errors. Any accuracy lever tuned against this run would be chasing noise.
Enrichment itself does not depend on GT, so a re-run on the corrected file
scores the *same* enrichment against correct GT.

## Done this session (safe, non-accuracy)

- Terminology (domain-term-alignment): recorded **field / enrichment field**
  as the canonical collective term for the trio (license name, license-file
  URL + download, copyright) in `docs/CONTEXT.md`. "element" and "item" are
  now under *Avoid* for prose; the `GT_ITEMS` code identifier is left as-is.
- Analysis of the run (read-only). Key numbers: wall 2421.7s, 380 rows;
  license infer = 70% of serial work (Σ33,080s, mean 87s), copyright 24%,
  download 6%; worker efficiency ~65% (19.6x effective of 30). 73/380
  downloads failed; copyright Unknown 158/380 (42%) — largely downstream of
  those failures.

## Terminology — remaining alignment

Canonical: **field / enrichment field**. Prose avoids "element" and "item"
for this meaning. `CONTEXT.md` glossary entry exists; live docs/code still
drift.

### Worth aligning

| Where | What it says today |
|---|---|
| `docs/CONTEXT.md` itself | **Scoring Outcome** still says “one inferred **item**” — internal contradiction with the new glossary entry |
| `docs/DECISIONS.md` | Heavy: “inference item”, “graded items”, “per-item triplet”, “enrichment item” — ~10 hits in Scoring / results-CSV sections |
| `src/scoring.py` | Identifier `GT_ITEMS` + docstring “graded item” |
| `src/results_csv.py` | Docstring “locked item order” |
| `src/summary.py` | Comment “GT item” |

### Leave alone

- `docs/plans/archive/v2-enricher/*` — historical record; rewriting would falsify the archive.
- `dict.items()`, checklist “Entry/Validation/Exit item”, unrelated “array elements” — not this meaning.
- Renaming `GT_ITEMS` → `GT_FIELDS` is optional churn (tests/imports). Prose/docs can say “field” while the identifier stays until someone wants the rename.

## Speed work — decided: nothing to build

- The only accuracy-neutral throughput lever is more parallelism, but
  `workers` is **LOCKED to 1..30** (`src/config.py:66`, `docs/DECISIONS.md:287`)
  and `configs/default.json` is already at 30. Omri decided this session to
  **keep the 1..30 bound** — so there is no speed code to build. Do not raise
  it without a new decision.
- `cache_read` speeds re-runs only (keyed on `component_name`, GT-independent).
  It is a per-run knob — pass an alternate config to `main.py` (argv[0]) with
  `cache_read: "caches"`; do NOT bake it into `default.json` (silent
  stale-cache footgun for fresh runs). The corrected-input re-run can use it
  to reuse this run's enrichment and score it fast against correct GT.

## Deferred accuracy plan (execute AFTER the corrected-input run)

Cheapest-first. Copyright is extracted only from a downloaded license file
(`src/pipeline.py:114-126`), so download fixes lift copyright for free.

1. Browser `User-Agent` on downloads — `_get_bytes` in `src/download.py:140-156`
   sends the default python-requests UA; hosts like `git.busybox.net` bounce
   it (busybox / busybox-binsh / ssl_client / ca-certificates-bundle failed in
   ~1s despite Claude returning the correct tag-pinned raw URL). Verify against
   one busybox `/plain/LICENSE?h=1_37_0` fetch before/after; if the host blocks
   regardless, those are genuine Unknowns, not a bug.
2. npm `author` copyright fallback — when file extraction returns UNKNOWN and
   the purl is `pkg:npm/...`, query `registry.npmjs.org/{pkg}` for `author`
   (`src/copyright.py` + caller). No extra LLM call. Cheap half of BACKLOG #4.
3. Investigate before building: `license_code_url` Mismatch rate. Sample ~15
   Mismatch rows from the run stories + `results_*_extended.csv` to classify
   valid-but-different file vs. genuinely wrong URL. Only then decide on a lever.
4. Parked in `docs/BACKLOG.md` (do NOT build speculatively): consistency judge
   (#1), broaden download fallback to NuGet/PyPI (#2), Claude-web copyright
   fallback (heavy half of #4).

## Commands run + results

- Run analysis: parsed `runs/20260715_013034_ClaudeOpu-4-8_380/` summary.json,
  score.csv, per_component/*/story.txt (read-only). No mutations.
- `git rev-parse --short HEAD` -> 945409e; `git status --short` -> clean.

## Test status

not run — no code changed this session (terminology + handoff are docs only).
If the worker cap is raised: update `src/config.py`, `configs/default.json`,
and `tests/test_config.py` (`test_workers_31_exits`), then `pytest -q`.

## Assumptions

1. The corrected input keeps the same `component_name`s (so cache reuse and
   apples-to-apples comparison hold). Verify at re-run time.
2. busybox-family download failures are UA-related, not host-blocked — must be
   verified (lever 1), not assumed.

## Open questions (Omri only)

1. For the corrected-input re-run, reuse this run's enrichment via
   `cache_read: "caches"` (fast, same enrichment), or run fresh (no cache)?
   (Resolved: `workers` cap stays LOCKED at 1..30 — no change.)

## Next action

Wait for Omri's re-run on the corrected input to produce a new `runs/` dir;
then implement deferred accuracy lever 1 (browser User-Agent in
`src/download.py` `_get_bytes`), verify against a `git.busybox.net` raw URL,
and re-check `score.csv` download-failure and copyright-Unknown counts.
