# Root-cause analysis — run `20260715_144424_ClaudeOpu-4-8_380`

Consumed: 2026-07-15 · Archived: 2026-07-19
Status: CONSUMED — embodied in `docs/plans/archive/fact-grade-tranche/`,
ADR-0006, and `docs/archive/DECISIONS_2026-07-15_fact-grade.md`.

Analyst: agent session, 2026-07-15. Scope: 380 components, audit mode,
model `claude-opus-4-8`, 30 workers, wall 62.8 min, total cost $131.80.

Source data: `runs/20260715_144424_ClaudeOpu-4-8_380/` (score.csv, summary.json,
`results_*_extended.csv`). Reproduction scripts:
`ad_hoc_scripts/analysis/{analyze_run,dump_examples,verify_urls,rescore}.py`;
raw dumps in `ad_hoc_scripts/ad_hoc_scripts_output/`.

---

## TL;DR

The headline `score.csv` looks weak (177/380 = **46.6%** all-three-Hit), but the
majority of the "misses" are **not agent errors**. They split into three very
different buckets:

1. **Ground-truth / methodology artifacts (~40% of all mismatches)** — the GT
   `license_code_url` is an HTML *landing page* (pkg.go.dev, pkgs.alpinelinux.org,
   nuget.org, changelogs.ubuntu.com), which our content-comparison cannot download,
   so the agent is marked wrong even though it found a valid license file. The
   single biggest lever is **not** on the agent.
2. **Judge over-strictness (~25% of mismatches)** — the GPT-4.1 equality judge
   fails "X" vs "X and Contributors", year-only differences, and EULA naming
   granularity, while (inconsistently) passing year differences elsewhere.
3. **Genuine agent gaps (~35% of mismatches)** — chiefly (a) **no NuGet download
   fallback** (Claude returns no URL for NuGet → empty → Mismatch), (b) a
   recurring **OpenTelemetry-Go copyright mis-extraction** ("The Go Authors"), and
   (c) Microsoft NuGet license-name defaulting to `Microsoft-EULA` when the source
   is actually MIT/Apache.

Under a transparent "fair-to-agent" re-grade (policy below), the score moves from
**46.6% → 62.1%** all-three-Hit, and per-field URL Hit-rate from **59.5% → 76.3%**.

| Field | Raw Hit | Adjusted Hit | Raw miss | Adjusted miss |
|-------|--------:|-------------:|---------:|--------------:|
| license_name      | 86.1% | 91.1% | 51 | 32 |
| license_code_url  | 59.5% | 76.3% | 154 | 52 (+38 → Unknown) |
| copyright         | 76.1% | 81.6% | 78 | 57 |
| **all-three-Hit** | **46.6%** | **62.1%** | — | — |

> The adjusted numbers are one defensible interpretation, not ground truth. They
> exist to show *where* the score is being lost, not to claim a "real" score.

---

## 1. The dominant problem: `license_code_url` (154 mismatches, 40.5%)

Because URL equality compares **downloaded file content** (ADR 0002), a URL
"Mismatch" means one of: the inferred URL didn't download, the GT URL didn't
download, or the two files' contents differ. The breakdown:

| Class | Count | Whose fault | Fix owner |
|-------|------:|-------------|-----------|
| `url_gt_not_a_file` (GT is a landing page) | 64 | **GT / methodology** | comparison logic |
| `url_proprietary_no_file` (EULA, empty inference) | 38 | neither (should be *Unknown*) | grading |
| `url_agent_missed` (OSS license existed, empty inference) | 32 | **agent** | download fallback |
| `url_content_differs` (judge FALSE) | 16 | mixed | judge / source pick |
| `url_agent_wrong` (inferred URL 404'd) | 4 | **agent** | URL construction |

### 1a. GT URL is a landing page, not a license file — 64 rows (biggest single cause)

The comparison ladder downloads the inferred URL *first*; it only reaches the GT
step if the inferred file downloaded OK. So **all 64 `gt_url_download_failed`
rows already have a working, downloadable license file from the agent** — they
fail only because the *ground-truth* URL is an HTML page our downloader (correctly)
rejects. Verified live (`url_verification.txt`):

- `pkg.go.dev/golang.org/x/sys@v0.29.0` → HTTP 200 `text/html` (all 21 golang rows)
- `pkgs.alpinelinux.org/package/.../tzdata` → HTTP 200 `text/html` (apk rows)
- `nuget.org/packages/.../License` → HTTP 200 `text/html`
- `changelogs.ubuntu.com/...` → HTTP 200 `text/html` (deb rows)

Example — `golang.org/x/sys@v0.29.0`: GT = `pkg.go.dev/...` (landing page);
agent = `raw.githubusercontent.com/golang/sys/v0.29.0/LICENSE` (the real file).
The agent is correct; the score says Mismatch.

**Representative fix (comparison side, no agent change):** when the GT URL is not
a fetchable license file (HTML content-type / known landing-page host), do **not**
grade URL by GT-content download. Fall back to comparing the *agent's* downloaded
license text against a canonical license for the declared SPDX id, or grade the
URL as "unscoreable / GT-not-a-file" rather than Mismatch. This alone recovers 64
rows.

### 1b. No NuGet download fallback — 70 empty inferences (`url_agent_missed` + `url_proprietary_no_file`)

Every empty-inference NuGet row shows the same story line:
`no claude url | non-npm purl: skip npm fallback`. Claude returns **no
`license_code_url` for NuGet**, and unlike npm there is no deterministic fallback
(`download.py:npm_candidates` is npm-only). Two sub-cases:

- **32 `url_agent_missed`** — OSS packages whose license *is* fetchable
  (`System.*`, `Microsoft.AspNet.*`, `EntityFramework`, dotnet/corefx). The agent
  should have found these.
- **38 `url_proprietary_no_file`** — genuine EULAs (DevExpress, ComponentSpace,
  Z.EntityFramework, Font Awesome Pro). No public license file exists; the correct
  grade is **Unknown**, not Mismatch. (Grading treats empty inference + FALSE eq as
  Mismatch; it should treat "no obtainable license" as Unknown.)

**Representative fix (verified live):** the NuGet flat-container API is a clean,
deterministic source:

```
https://api.nuget.org/v3-flatcontainer/{id-lower}/{version}/{id-lower}.nuspec
```

Probed results (`url_verification.txt`):

- `Newtonsoft.Json@13.0.3` → `<license type="expression">MIT</license>`,
  `repository url=github.com/JamesNK/Newtonsoft.Json` → fetch `LICENSE` from repo.
- `Microsoft.AspNet.WebApi.Core@5.2.7` → `repository=github.com/aspnet/AspNetWebStack`
  → repo `LICENSE.txt` = Apache-2.0.
- Legacy packages (`System.Collections@4.3.0`, `EntityFramework@6.2.0`) →
  `licenseUrl=go.microsoft.com/fwlink/...` (the legacy .NET Library EULA) with no
  SPDX and no repo. These are the genuinely ambiguous cases (see §4).

This directly matches **BACKLOG Lever #2** ("broaden deterministic download
fallback beyond npm/unpkg") — the trigger condition is now met.

### 1c. Agent URL construction errors — 4 rows

`binutils` (`.../binutils-2_45_1/COPYING` → 404), `busybox`/`ssl_client`
(`git.busybox.net/.../LICENSE?h=1_37_0` → 404). Wrong tag/ref or path. Low volume;
a retry-with-alternate-ref or the deterministic fallback above would catch most.

---

## 2. `copyright` (78 mismatches, 20.5%)

All 78 reached the GPT-4.1 judge (none are download failures). Classes:

| Class | Count | Interpretation |
|-------|------:|----------------|
| `cp_different_holder` | 54 | mostly genuine, but see OTel cluster below |
| `cp_year_or_format_only` | 12 | **judge over-strict** — same holder, different year/format |
| `cp_superset_subset` | 9 | **judge over-strict** — "X" vs "X and Contributors" |
| `cp_partial_overlap` | 3 | debatable |

### 2a. Genuine, recurring agent error: OpenTelemetry-Go → "The Go Authors" — 13 rows

Every `go.opentelemetry.io/otel/*` row extracted `Copyright 2009 The Go Authors.`
instead of the correct `The OpenTelemetry Authors`. Verified: the OTel-Go LICENSE
is a bare Apache-2.0 template (no holder line), so the real notice lives in file
headers / NOTICE, not `LICENSE`. The extractor latched onto a Go-stdlib BSD notice
("Copyright 2009 The Go Authors") instead. This is the largest *genuine* copyright
error and is highly systematic (one upstream family).

**Representative fix:** for Apache-2.0 licenses whose `LICENSE` has no
`Copyright ...` holder line, extract the holder from `NOTICE` / source-file
headers rather than accepting an unrelated stray notice; or fall back to the
package's declared author. Add a guard: reject a copyright holder that is
lexically unrelated to the package/repo owner.

### 2b. Judge over-strictness — 21 rows (12 year-only + 9 superset)

- **Year-only (12):** e.g. `genproto` GT `Copyright 2025 Google LLC` vs INF
  `Copyright 2026 Google LLC` → judged FALSE on the year. Yet elsewhere the judge
  *passed* a year difference (`DevExpress` GT `1998-2026` vs INF `2000-2019` = Hit).
  The judge is **inconsistent** on years.
- **Superset (9):** `X` vs `X and Contributors` (yallist, chownr, package-json-from-dist,
  `Microsoft.Extensions.*` `.NET Foundation` vs `.NET Foundation and Contributors`).
  The primary holder matches; the judge fails on "and Contributors".

**Representative fix:** tighten the judge prompt (`prompts.equality_copyright_prompts`)
to (a) ignore year/date ranges when the holder matches, and (b) treat a
GT-holder-set that is a subset/superset of the inferred set (esp. "and
Contributors") as equal. This makes the judge deterministic on the two commonest
false-negatives.

### 2c. apk/system "GT is a hand-summary, INF is the raw multi-holder list"

Many apk rows (python3, icu-*, tiff, ncurses, musl, libx11) have a GT that is a
*curated* holder summary while the agent extracted the *complete* list of copyright
lines from the actual license file. These are a methodology mismatch (what counts
as "the copyright"?) more than an agent error — but they are legitimately hard and
I left them as Mismatch in the adjusted score (conservative).

---

## 3. `license_name` (51 mismatches, 13.4%)

| Class | Count | Interpretation |
|-------|------:|----------------|
| `ln_eula_naming_granularity` | 17 | naming granularity — `Microsoft-EULA` vs `Microsoft .NET Library License` |
| `ln_agent_said_eula_but_oss` | 17 | **agent** — said `Microsoft-EULA`, GT is MIT/Apache |
| `ln_other` | 8 | mixed (DevExpress Commercial vs NonCommercial, etc.) |
| `ln_spdx_expression` | 7 | compound SPDX subset/superset (apk/deb) |
| `ln_synonym` | 2 | `ICU` vs `Unicode-3.0` (same license, different name) |

### 3a. Genuine agent error — 17 rows: Microsoft NuGet defaulting to `Microsoft-EULA`

`System.*@4.3.0`, `Microsoft.VisualStudio.Azure.Containers.Tools.Targets`,
several `Microsoft.AspNet.*` → agent said `Microsoft-EULA`, GT says `MIT`/`Apache-2.0`.
For modern dotnet OSS packages this is a real recall miss (the source is MIT/Apache).
**Nuance:** for some legacy packages the nuspec genuinely declares the .NET Library
EULA (`net_library_eula`), so the agent's `Microsoft-EULA` is arguably right and the
GT is debatable (see §4). The NuGet-nuspec fallback (§1b) fixes both — it returns
the declared SPDX id when present.

### 3b. Naming granularity / synonyms — 19 rows (judge/normalization)

`Microsoft-EULA` vs `Microsoft .NET Library License` (17), `ICU` vs `Unicode-3.0`
(2). Same underlying license, different label. A small SPDX-synonym normalization
table + a judge instruction to treat generic-vs-specific EULA labels as equal would
recover these.

### 3c. Compound SPDX expressions — 7 rows (debatable, left as Mismatch)

`GPL-2.0-or-later AND LGPL-2.1-or-later` vs `GPL-3.0-or-later WITH GCC-exception-3.1`
(libatomic/libgomp — agent arguably *more* correct), `LGPL... AND GPL...` vs a
subset, `xz-libs` `0BSD` vs an over-broad list. Genuine SPDX-expression disagreements;
these need a set-aware SPDX comparator, not a string match.

---

## 4. Ground-truth quality caveat (affects all three fields)

Some "mismatches" are cases where the **agent is at least as correct as the GT**:

- `Microsoft.AspNet.WebApi.Core@5.2.7`: repo `LICENSE.txt` is literally
  `Copyright (c) .NET Foundation ... Apache License 2.0`. Agent said
  `Apache-2.0` / `.NET Foundation`; GT said `Microsoft .NET Library License` /
  `Microsoft Corporation`. Agent is arguably right, scored as double Mismatch.
- `System.Collections@4.3.0`: nuspec `licenseUrl` = legacy .NET Library EULA, but
  GT = `MIT`. Genuinely ambiguous (declared license vs source license).
- `libatomic`/`libgomp`: agent's `GPL-3.0-or-later WITH GCC-exception-3.1` is the
  accepted license for these GCC runtime libs; GT is a different combo.

These cannot be "fixed" in the agent; they argue for GT review and for reporting an
"agent-vs-GT disagreement, source-ambiguous" bucket rather than a flat Mismatch.

---

## 5. Prioritized recommendations

| # | Action | Est. rows recovered | Effort | Fault |
|---|--------|--------------------:|--------|-------|
| 1 | **Fix URL grading when GT is not a fetchable file** (don't penalize a valid inferred license against an HTML GT landing page) | ~64 | low (grading/eq logic) | GT/method |
| 2 | **Add NuGet deterministic fallback** via `api.nuget.org` nuspec (SPDX + repo LICENSE) — BACKLOG Lever #2 | ~32 URL + ~17 name | med | agent |
| 3 | **Grade "no obtainable license" as Unknown, not Mismatch** (EULAs) | ~38 (Mismatch→Unknown) | low | grading |
| 4 | **Tighten copyright judge**: ignore years when holder matches; treat subset/"and Contributors" as equal | ~21 | low (prompt) | judge |
| 5 | **Fix OpenTelemetry-Go copyright extraction** (Apache LICENSE w/o holder → use NOTICE/headers; reject unrelated holders) | 13 | med | agent |
| 6 | **SPDX synonym + generic-EULA normalization** for license names | ~19 | low | judge/norm |
| 7 | **SPDX-expression set comparator** for compound licenses | ~7 | med | method |

Items 1, 3, 4, 6 are grading/judge changes (cheap, high-yield, ~124 rows of
apparent misses that are not agent errors). Items 2 and 5 are the real agent
improvements. This also re-triggers **BACKLOG Lever #1** (consistency judge) since
license inference does have genuine gaps.

---

## Appendix — artifacts

- `ad_hoc_scripts/analysis/analyze_run.py` — per-field tallies + URL breakdown
- `ad_hoc_scripts/analysis/dump_examples.py` — per-category example dumps
- `ad_hoc_scripts/analysis/verify_urls.py` — live URL probes + NuGet API test
- `ad_hoc_scripts/analysis/rescore.py` — root-cause classification + adjusted score
- `ad_hoc_scripts/ad_hoc_scripts_output/` — all generated `.txt` outputs
