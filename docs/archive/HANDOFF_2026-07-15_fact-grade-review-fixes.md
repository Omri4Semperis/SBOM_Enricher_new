# HANDOFF — implement the 6 fixes from the fact-grade tranche review

Consumed: 2026-07-15 — planned as `docs/plans/fact-grade-review-fixes/` (P1
download hardening, P2 association-aware holder guard, P3 honest re-score).

- Objective: Address every finding in `docs/full-review_fact-grade-tranche.md`
  (1 blocker, 4 should-fix, 1 nit) so the fact-grade tranche can be signed off.
  Decisions on HOW to fix each were settled in a grilling session (below).
- Repo: `C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve sbom-enricher agent/SBOM_Enricher_new`
- Branch: `master`
- HEAD: `d532a16`
- Dirty: 1 uncommitted path (`docs/full-review_fact-grade-tranche.md`, untracked;
  this handoff adds a second)

## Files changed

No implementation started yet — the fixes below are all still TODO.

- `?? docs/full-review_fact-grade-tranche.md` — the review being actioned (untracked).
- The tranche under review was committed in range `330b0c4..144a8b6` (already
  merged into `master`, now at `d532a16`).

## Decisions (from grilling — how to fix each finding)

- **B1 (blocker) — `src/download.py:159` `nuget_candidates`**: A non-GitHub
  `<repository url>` is reduced to `owner/repo` and rewritten to
  `raw.githubusercontent.com`, so an unrelated GitHub repo of the same name can
  have its license silently attributed. Fix: require a recognized GitHub host
  (`github.com`/`www.github.com`) before constructing the raw URL; return `[]`
  for any other host. Add a non-GitHub collision test.
- **S1 (should-fix) — `src/copyright.py:32` `_is_stray_holder`**: Holder-only
  denylist wrongly rejects legitimate Go/Android packages. Fix: make it
  association-aware — pass `purl`/`lib_name` in and reject a stray holder only
  when the package is NOT of that family. Use a per-holder rule, each with its
  own matcher: "The Go Authors" rejected only for non-`pkg:golang/` purls; AOSP
  ("The Android Open Source Project") allowed only when purl/lib_name carries a
  known Android marker (e.g. `android`). Test a legit Go holder kept + a stray
  association rejected. **ADR REQUIRED** for this decision (see Open questions).
- **S2 (should-fix) — `src/download.py:317`**: The synchronous nuspec
  `requests.get` runs inside the asyncio loop, freezing every worker. Fix: call
  it via `await asyncio.to_thread(nuget_candidates, purl)` (mirrors the existing
  npm fallback). Add a concurrency regression test.
- **S3 (should-fix) — `src/download.py:132`**: Flat-container endpoint needs a
  NuGet-normalized, lowercased version, but the purl version is used verbatim.
  Fix: full normalization — URL-decode, strip SemVer build metadata (`+...`),
  lowercase, strip leading zeros per numeric segment, drop a zero-valued 4th
  segment (`1.0.0.0`→`1.0.0`). Test an uppercase prerelease version.
- **S4 (should-fix) — `ad_hoc_scripts/analysis/rescore.py:85`**: Blanking a
  rejected copyright and grading it forces `Unknown`, but production continues
  through npm + Claude-web fallbacks. Fix: stop asserting a resulting grade for
  stray-holder rows — report only the guard-trigger count. Correct the
  "20 of the 78 raw-Mismatch rows → Unknown" claim in
  `docs/archive/2026-07-15_run-144424_fact-grade-rescore.md` (lines ~68–102).
- **N1 (nit) — `src/download.py:321`**: A valid `pkg:nuget/` purl whose lookup
  yields no candidates is logged as "non-nuget purl", hiding the real failure.
  Fix: if the purl starts with `pkg:nuget/` but yielded no candidates, log
  `nuget: no candidates (nuspec/repo lookup failed)`; else keep
  `non-nuget purl: skip`.

## Commands run + results

- `git diff --name-status 330b0c4..144a8b6` → confirmed the tranche's committed
  file set (src + tests + docs); no new commits pending from this session.
- Test suite: not run this session. Review census recorded `130 passed in 13.42s`
  on the reviewed tranche.

## Test status

not run this session. Baseline from the review: `130 passed in 13.42s`.

## Assumptions

1. "Recognized GitHub host" (B1) means `github.com` and `www.github.com` only;
   no other GitHub-owned hosts are in scope.
2. The generated analysis doc to correct for S4 is
   `docs/archive/2026-07-15_run-144424_fact-grade-rescore.md` (verified to
   contain the "20 ... → Unknown" claim).

## Open questions

1. **ADR scope** — the user explicitly requires an ADR for the **S1**
   association-aware stray-holder decision. Confirm whether the **B1** cross-host
   license-attribution policy ("never derive a GitHub raw URL from a non-GitHub
   repository field") should also get its own ADR, or be folded in. Author ADRs
   via the `domain-modeling` skill; next ADR number is `0007`
   (latest is `docs/adr/0006-unscoreable-grade.md`).

## Next action

Implement **B1** in `src/download.py` `nuget_candidates`: gate raw-URL
construction on a recognized GitHub host, return `[]` otherwise, and add a
non-GitHub collision test in `tests/test_download.py`. Then proceed down S2, S3,
S1 (+ ADR 0007), S4, N1, and finally re-run the test suite.
