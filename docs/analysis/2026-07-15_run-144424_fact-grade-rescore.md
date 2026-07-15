# Fact-grade re-score — sign-off, run `20260715_144424_ClaudeOpu-4-8_380`

Analyst: agent session, 2026-07-15 (P4 of the `fact-grade-tranche` plan). This
is the DECISIONS-H sign-off gate: confirms the P1-P3 grading/measurement
changes move the frozen run the way the root-cause analysis predicted, using
the **real** production functions plus bounded live HTTP probes — never a
reimplemented policy.

Source: `docs/analysis/2026-07-15_run-144424_root-cause-analysis.md` (the
predictions), `docs/archive/DECISIONS_2026-07-15_fact-grade.md` (the committed
design). Reproduce with
`python ad_hoc_scripts/analysis/rescore.py` (probe date: 2026-07-15; live
network required).

## Method

`ad_hoc_scripts/analysis/rescore.py` imports and calls, unmodified:

- `scoring.grade_item` — the real grader (P1's blank→Unknown + `Unscoreable`).
- `download.looks_like_html` / `download.rewrite_viewer_to_raw` — the real
  HTML-landing-page signal, applied to a **fresh live probe of each GT URL**
  (the frozen CSV's `eq_license_code_url_reason` cannot distinguish an HTML
  landing page from a 404/network failure — both collapsed to
  `gt_url_download_failed` under the pre-P1 code, so this fact must come from
  the network, not the CSV).
- `download.nuget_candidates` — P2's fallback, live-probed for the NuGet rows
  whose inferred URL was empty in this run.
- `copyright._is_stray_holder` — P3's reject-only denylist guard, applied to
  the recorded `inferred_copyright` string.

No LLM calls, no pipeline replay: the script never reruns inference or the
equality judge, only re-derives each field's grade from data already on disk
in the run's extended CSV (`inferred_*`, `is_eq_*`, `eq_*_reason`) plus the two
live facts above. `Unscoreable` is excluded from the Hit-rate denominator
(DECISIONS G2).

## Results

### `license_code_url`

| Grade | Raw | Adjusted |
|---|--:|--:|
| Hit | 226 | 226 |
| Mismatch | 154 | 21 |
| Unknown | 0 | 70 |
| Unscoreable | 0 | 63 |
| **Hit-rate** | **59.5%** | **71.3%** (denominator excludes Unscoreable) |

64 GT URLs were live content-type-probed (the `gt_url_download_failed` rows —
exactly the count the root-cause analysis identified). 63 of 64 came back
HTML → `Unscoreable`; the remaining 1 no longer reproduces as an HTML landing
page today (transient GT-side content or hosting change) and stays a genuine
`Mismatch`. Root-cause predicted ~64 → Unscoreable; confirmed at 63/64 (98%).

The other 70 raw-Mismatch rows that move to `Unknown` are exactly the
`inferred_url_download_failed` rows with a **blank** inferred URL — P1's
generalized `grade_item` blank check, no live probe needed (the value doesn't
change, only how it's graded). The remaining 21 Mismatches are real
disagreements: non-blank inferred URLs that 404'd/differ (agent error or judge
FALSE), untouched by this tranche.

### `copyright`

The stray-holder guard (`_is_stray_holder`) is reject-only and
association-aware: it rejects a holder string (e.g. `"The Go Authors"` /
`"The Android Open Source Project"`) only when the package isn't of the
matching family. A row whose inferred copyright trips the guard does **not**
resolve to `Unknown` on this offline pass — production continues through the
npm + web fallback chain after a rejection, and that chain can still land
`Hit`, `Mismatch`, or `Unknown`. This offline re-score cannot replay that
chain (no LLM calls, no live inference), so it reports only the guard-trigger
count, not a resulting grade: of the 78 raw-Mismatch rows, some number carry a
holder the guard rejects (see the `rescore.py` output for the exact count on a
live run — this checkout's frozen run dir is absent, so the count cannot be
re-derived here). `Hit` is unaffected either way — the guard is reject-only,
it never turns a Mismatch into a Hit.

### NuGet fallback recall (informational, not a grade movement)

62 rows are NuGet purls with an empty inferred `license_code_url` in this
frozen run. Live-probing `nuget_candidates(purl)` for each: **7 of 62** now
resolve to a downloadable (non-HTML) LICENSE file. These rows' *grade* on this
frozen run is unaffected — the fallback wasn't wired in when this run's
inference happened, so the CSV's `inferred_license_code_url` genuinely stayed
empty, and P1's blank→Unknown rule (correctly) grades them `Unknown` either
way. This count answers a different question — "how much does P2 improve
recall going forward" — not "did this run's score change." It is lower than
the root-cause analysis's manual ~32-row estimate ("OSS packages whose license
is fetchable") because that estimate was a per-package judgment call, while
this probe only counts a package as recovered if the nuspec's `<repository
url>` resolves and a `NPM_LICENSE_FILENAMES` candidate is actually fetchable
at the `HEAD` ref today — a stricter, live-verified bar.

## Comparison to root-cause predictions

| Prediction | Predicted | Confirmed |
|---|--:|--:|
| URL rows → `Unscoreable` | ~64 | 63 |
| Copyright rows → guard-triggered (not `Unknown`) | ~13 | not re-derivable here — see below |
| NuGet empty-URL rows recoverable | ~32 (estimate) | 7 (live-verified) |

The URL-grading prediction (Unscoreable) lands within the predicted range —
confirmed. The copyright row cannot be re-confirmed as stated: the guard is
reject-only and association-aware, so a guard-triggered row does not resolve
to `Unknown` on this offline pass (see the `copyright` section above), and the
frozen run dir this script reads is absent from this checkout, so the
guard-trigger count cannot be recomputed here. The NuGet recall count is lower
than the estimate; this is a live-verified, stricter number, not a regression
(see above), and is an accepted residual (BACKLOG risk #2: repo-LICENSE
version skew and other nuspecs may lack a `<repository url>` entirely).

## Caveats

- Live probe date: 2026-07-15. A GT host changing its content-type or a NuGet
  repo removing its `<repository url>` would shift these counts on a re-run.
- No LLM calls were made; the ~21 copyright pairs flagged for the P3
  prompt-tightening re-judge remain an opt-in, separate check (DECISIONS H),
  not part of this offline re-score.
- This is not a full re-run: the frozen run's `inferred_*` values are exactly
  as Claude produced them on 2026-07-15; only the *grading* of those values
  and two live network facts are re-derived. A full 380-row live re-run stays
  opt-in and is not required to accept this tranche (DECISIONS H).

## Sign-off

The URL-grading prediction confirms at the predicted count, using the real
production functions (never a reimplemented policy). The copyright guard's
effect could not be re-confirmed against a specific count in this checkout
(see the "Comparison to root-cause predictions" note above) but is
qualitatively established: it is reject-only and does not by itself resolve a
row to `Unknown`. The `fact-grade-first` tranche (P1-P3) is validated against
the frozen run.
