# Full review — fact-grade tranche

Consumed: 2026-07-15 — every finding planned into
`docs/plans/fact-grade-review-fixes/` (B1→P1, S1→P2, S2/S3/N1→P1, S4→P3).

## Executive summary

The tranche adds truthful `Unscoreable`/blank grading, a NuGet nuspec fallback,
copyright-holder rejection, scoped judge guidance, and an offline re-score. The
core grading path is well tested, but the NuGet fallback can silently download an
unrelated GitHub repository's license when a nuspec names another host. The
copyright guard and re-score also make claims broader than the evidence supports.
This needs work before the tranche is treated as signed off.

Review scope: committed implementation `330b0c4..144a8b6`, excluding unrelated
current worktree edits and the incidental planning-skill template change.

## Blockers

- `src/download.py:159` — A non-GitHub `<repository url>` is reduced to its first two path segments and converted to `raw.githubusercontent.com`; if that owner/repo happens to exist on GitHub, the pipeline can accept and attribute an unrelated license. Require a recognized GitHub host before constructing this URL (or implement the repository host's real raw-URL form), return `[]` otherwise, and add a non-GitHub collision test.

## Should-fix

- `src/copyright.py:32` — The holder-only denylist cannot establish that “The Go Authors” or AOSP is unrelated to the current package, so it rejects legitimate Go/Android components too. Replace it with association-specific rules keyed by holder plus known affected package family, passing `purl`/`lib_name` into the predicate, and test both a known stray association and a legitimate holder.
- `src/download.py:317` — `nuget_candidates()` performs a synchronous 30-second HTTP request inside the asyncio worker loop, temporarily stopping every configured worker. Call it through `await asyncio.to_thread(...)` and add a concurrency regression test.
- `src/download.py:132` — The flat-container endpoint requires a lowercased, NuGet-normalized version, but the code uses the purl version verbatim. Normalize and lowercase the decoded version (including removing SemVer build metadata) and test an uppercase prerelease version.
- `ad_hoc_scripts/analysis/rescore.py:85` — Blanking a rejected frozen copyright and grading it `Unknown` does not reproduce production, which continues through npm and web fallbacks and may end as Hit, Mismatch, or Unknown. Report only the guard-trigger count unless the complete resolver chain is replayed, and correct the 20-row Unknown claim in the generated analysis.

## Nits

- `src/download.py:321` — A valid NuGet purl whose nuspec fetch fails or lacks a repository is logged as “non-nuget purl,” obscuring the actual fallback failure. Distinguish a non-NuGet purl from a NuGet lookup that produced no candidates.

## Census

- Native test gate: `130 passed in 13.42s`.
- File-length threshold: `tests/test_copyright.py` is 429 lines (threshold 400); informational, not a verdict item.
- Test/source presence ratio: `0.8947` (17 test files / 19 source files).
- Deferred shortcut: `src/download.py:164` records the HEAD-ref ceiling with a concrete upgrade trigger.
- No long-line, TODO, generated/vendored, or oversized-file breaches. The risky-pattern scan only matched the standard HTTP XML namespace literals in test nuspec fixtures.

Verdict: reject
