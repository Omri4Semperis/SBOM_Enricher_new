# Accuracy review — run `20260716_160137_ClaudeSon-5_220`

Analyst: agent session, 2026-07-16. Question posed: **do the runtime-report
hit-rates reflect our real accuracy?** Method: sample-based inspection of the
Mismatch / Unknown / Unscoreable buckets using the run's own artifacts
(`results_*_extended.csv` GT-vs-inferred + judge reasons, the downloaded
license files on disk) plus a few targeted live web checks. Not an exhaustive
per-component re-score — representative cases only.

Model: `claude-sonnet-5`, 20 workers, 220 GT rows, 3 hard failures.

> **Status: findings not yet incorporated into the app.** This is analysis
> only — no code/scoring changes were made. Pending work (grader/reporting
> changes + a reporting-policy grilling session) is tracked in
> `docs/HANDOFF.md`.

## Headline numbers (as reported)

Hit-rate = Hit / (Hit + Mismatch + Unknown); Unscoreable excluded from the
denominator (`scoring.py`, DECISIONS G2).

| Field | Hit | Mismatch | Unknown | Unscoreable | Hit-rate |
|-------|----:|---------:|--------:|------------:|---------:|
| license_name      | 181 | 34 |  2 |  0 | 83% |
| license_code_url  | 133 | 10 | 37 | 37 | 74% |
| copyright         | 148 | 63 |  6 |  0 | 68% |

Run economics: **~$0.30/row** (~$66 total), **~14 s/row** parallelized
(~51 min wall), **~13.4 h** serial-equivalent (sum of per-row elapsed).

## Verdict

**The reported rates understate true accuracy.** A large fraction of the
non-Hit rows are ground-truth-quality or judge-strictness artifacts, not
enrichment errors.

## 1. Mismatches — a mix of real errors and false negatives

Real errors (we are wrong):

- **DevExpress.\* license → `Microsoft-EULA`** (7 pkgs). Wrong vendor. We
  collapse any proprietary EULA to the literal string "Microsoft-EULA".
- **Confluent.SchemaRegistry copyright → `Andreas Heider`** (verified live).
  The shared Apache LICENSE carries an old upstream contributor; extraction
  picked it over the package owner. GT `Confluent Inc.` is correct.

False mismatches (we are right / defensible; GT or judge is the issue):

- **`.NET Foundation` vs GT `Microsoft Corporation`** (WebApi, NETStandard,
  System.Runtime.Numerics…). The downloaded license file literally reads
  `Copyright (c) .NET Foundation and Contributors` — our answer matches the
  shipped file; GT is the outlier.
- **Microsoft.VisualStudio.Azure.Containers.Tools.Targets → `Microsoft-EULA`**
  (verified live): the nuget package license is "MICROSOFT SOFTWARE LICENSE
  TERMS", not MIT. GT (`MIT`) is wrong here; we are right.
- **DevExpress copyright "mismatches"**: same holder (`Developer Express
  Inc.`), only year ranges differ (we read the range from the actual v19.1.5
  file; GT uses a current-year range). Flagged by the judge's ±1-2yr tolerance.
- **Normalization nitpicks**: `Isaac Z. Schlueter` vs `…and Contributors`;
  `ZZZ Projects` vs `ZZZ Projects Inc.`; `Public Domain` vs `Pubic Domain
  (SQLite Blessing)` [sic]; `LGPL-3.0-only` vs `-or-later`; `Libpng` vs
  `libpng-2.0`. Substantively equal.

## 2. Unknowns (mostly URL) — mostly findable, discarded by design

The 37 URL Unknowns are almost all `inferred_url_download_failed`, **not**
"couldn't find it". Claude's reasoning names the correct license page in most
cases (DevExpress EULA, `fontawesome.com/license`,
`microsoft/DockerTools/LICENSE.txt`, `sqlite.org/copyright.html`, corefx
`LICENSE.TXT`), but the download validator rejects HTML EULA/landing pages and
blanks the field → graded Unknown. We locate them; we drop them because they
aren't raw downloadable files.

- Genuinely unknown: Font Awesome Pro / `@awesome.me` kit (auth-gated registry).
- One real infra failure: `DevExpress.Wpf.Themes.Office2016White` — Claude
  subprocess timed out at 1200 s.

## 3. Unscoreable — our findings look valid, often better than GT

All 37 are `gt_not_a_file`: the **GT** URL is an HTML landing page
(`pkg.go.dev/…`, `pkgs.alpinelinux.org/…`, `nuget.org/…/License`, gitlab/github
`blob`/`tree` pages, `changelogs.ubuntu.com`). Our inferred URL is a genuine
raw license file:

- `golang.org/x/*` → `raw.githubusercontent.com/golang/<mod>/<ver>/LICENSE`
- `Microsoft.AspNet.WebApi.*` → `…/aspnet/AspNetWebStack/…/LICENSE.txt`
- Alpine pkgs → upstream `COPYING`/`LICENSE` on github/gitlab

Without GT we would rightly accept these — they download to real, matching
license text. Unscoreable here is a GT limitation, not our failure. Only 2 are
weak: `ca-certificates-bundle` and `tzdata` point to `APKBUILD` (a build
script, not license text).

## How to improve the scores

Two independent levers. The reported number moves for **either** reason, so
separate them or the report keeps lying in a new way.

### A. Raise real enrichment accuracy (fix actual defects)

1. **Generic-EULA labeling** — stop collapsing all proprietary EULAs to the
   literal `Microsoft-EULA`; emit the actual vendor (`DevExpress …EULA`,
   `ComponentSpace …EULA`). Fixes ~7 DevExpress license mismatches outright.
2. **Copyright holder selection** — extraction can pick a stray upstream
   contributor from a shared LICENSE (Confluent → `Andreas Heider`); bias
   toward the package/owner holder (nuspec `<authors>`/`<copyright>`, npm
   `author`) over the oldest name in the file.
3. **Keep a correctly-identified HTML license page instead of blanking it** —
   many URL "Unknowns" are cases where Claude named the right EULA/license
   page but the download validator rejected the HTML body. Options: retain the
   URL (even if we can't download a raw file), or add a text-extraction path
   for known EULA hosts (nuget `…/License`, devexpress, fontawesome). Recovers
   a big chunk of the 37 URL Unknowns.
4. **Version-pinned raw-file fallback for registry/landing purls** (golang
   `x/*`, Alpine, corefx) — we already infer the correct raw URL in the
   Unscoreable set; make it the primary answer.

### B. Fix what/how we measure and report (the bigger lever here)

The reported rates understate reality mostly because of the scoring policy and
GT quality, not the enricher:

1. **GT quality pass** — a large share of "misses" are GT problems: GT URLs
   that are HTML landing pages (→ Unscoreable), and GT license/copyright values
   that disagree with the shipped artifact (`MIT` vs the package's real EULA;
   `Microsoft Corporation` vs the file's `.NET Foundation`). Clean or re-source
   GT, or mark low-confidence GT cells so they don't count against us.
2. **Judge strictness knobs** — the copyright year-tolerance flags
   same-holder notices as mismatches; decide whether holder-match alone should
   score as Hit (report "holder Hit / exact Hit" as two tiers).
3. **Report Unscoreable honestly** — it's currently excluded from the
   denominator, which is defensible, but the headline hides that ~17% of URL
   rows are ungradeable *because of GT*. Surface an "un-gradeable" line so the
   reader isn't misled either way.
4. **Confidence / provenance in the report** — when our answer is backed by a
   downloaded file that contradicts GT, that's signal the report throws away.
   Consider a "we-disagree-with-GT-and-here's-the-file" bucket.

### C. Decide what we actually want to report (grilling session)

We just established the headline rates don't reflect reality — but "reality"
itself is contested (whose license is canonical: the source repo's, or the
shipped package's EULA?). Before changing the grader, run a **grilling session**
(`grilling` skill) to pin down:

- What does "correct" mean per field — the source-repo license, or the license
  the distributed artifact ships under? They genuinely differ (System.\* 4.3.0,
  the VS Container Tools package).
- Do we report accuracy-vs-GT, or accuracy-vs-truth (accepting GT can be
  wrong)? These are different numbers and different audiences.
- Hit tiers: is holder-match-but-year-differs a Hit, a partial, or a miss?
- How to treat un-gradeable-due-to-GT rows in the headline.
- What number goes in front of a customer vs. an internal quality dashboard.

Output of that session → an ADR (`docs/adr/`) defining the reporting contract,
then implement B (grader/report) and A (enricher).

## Follow-up not done here

A full-run re-classification of the 34 license + 63 copyright mismatches into
"real error" vs "GT/judge artifact" to put a hard number on the true-accuracy
gap. Deferred to the incorporation work (see `docs/HANDOFF.md`).
