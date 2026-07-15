# Plan: fact-grade-first tranche

**Live document.** Unlike the old design, this file is written to during
execution. The executor of phase N may edit **only two files**: its own
`P{N}_{...}.md` doc and this `PLAN.md`. It updates its row in the phase
table, reflects concise notes into its own per-phase block, and leaves
**Incoming comments** in *another* phase's block here when it discovers
something that phase must know. It never edits another phase's `P*` doc.

**Execution:** one phase per fresh session via the `complex-plan-implement-phase`
skill. Fallback without that skill: pick the lowest-numbered phase whose
**Depends on** entries are all `done` in the table below and whose own Status
is `pending`; then follow that phase doc top to bottom — its Entry criteria,
Tasks, Validation gate, Exit criteria, and On completion sections are the
complete procedure. Read this whole `PLAN.md` first for cross-phase context
and any Incoming comments left in your phase's block.

## Goal

Implement the signed-off "fact-grade-first" tranche from `docs/DECISIONS.md`:
make the audit **measurement more truthful** without gaming the headline
number. Three real changes — stop scoring the agent when the ground-truth URL
is a landing page (not a file), find a downloadable LICENSE for NuGet packages,
and stop emitting a wrong copyright holder — plus one prompt-tightening and the
durable-doc updates they force. Raising the all-three-Hit rate is an **explicit
non-goal**; every change either measures more honestly or genuinely improves
recall.

## Context

Python 3, Windows/PowerShell. Source under `src/` (bare imports; `tests/conftest.py`
puts `src/` on the path). The enrichment pipeline (`src/pipeline.py`
`process_component`) infers three fields per component — license name, a
downloadable license-file URL, and copyright — then, in **audit mode** (input
has ground-truth columns), `apply_equality` fills `is_eq_*` verdicts and
`grade_row` assigns a per-field **grade**. See `.cursor/skills/architecture-overview`
and `docs/CONTEXT.md` for the map and vocabulary.

Modules this plan touches:

- `src/download.py` — license-file fetch (URL rewrite, HTML reject, npm fallback).
  `fetch_license_file(claude_url, purl, dest_dir, slug) -> DownloadResult`.
- `src/equality.py` — audit equality ladders. `compare_url_content(...)` returns
  an `EqResult(verdict, reason, meta)`; `verdict` is `TRUE`/`FALSE` today.
- `src/scoring.py` — `grade_item(inferred, is_eq) -> "Hit"|"Mismatch"|"Unknown"`;
  `grade_row` calls it per field.
- `src/copyright.py` — `resolve_copyright` chain: file → npm author → web → UNKNOWN.
- `src/prompts.py` — prompt/schema builders, incl. the shared `EQUALITY_JUDGE_SYSTEM`
  and `equality_copyright_prompts`.

Frozen evidence run for offline re-score: `runs/20260715_144424_ClaudeOpu-4-8_380/`
(extended CSV + downloaded license files on disk). Do not delete it.

**Cross-phase constraint (from DECISIONS G3):** the NuGet fallback (P2) should be
in place before "blank inference → Unknown" (added in P1) is *interpreted* — an
OSS license that P2 would have found must not be read as "agent didn't answer".
The code changes are independent and either order compiles/tests green; the
constraint only binds the offline re-score (P4), which depends on both. No false
code dependency is imposed between P1 and P2.

## Phases

| Phase                                                  | Purpose                                                                 | Depends on | Status  | Baseline | Updated |
| -                                                      | -                                                                       | -          | -       | -        | -       |
| [P1: grading_honesty](./P1_grading_honesty.md)         | `Unscoreable` URL grade (GT-not-a-file) + blank inference → Unknown + docs | -          | done    | 330b0c4  | 2026-07-15 |
| [P2: nuget_nuspec_fallback](./P2_nuget_nuspec_fallback.md) | NuGet nuspec → repo LICENSE file for the URL field                    | -          | done | 453f143  | 2026-07-15 |
| [P3: copyright_honesty](./P3_copyright_honesty.md)     | Reject-only copyright denylist guard + judge copyright prompt-tightening | -          | pending |          |         |
| [P4: offline_rescore_signoff](./P4_offline_rescore_signoff.md) | Offline re-score sign-off gate over the frozen run             | P1, P2, P3 | pending |          |         |

## Test commands

| Purpose    | Command                                    | Expected                                              |
| -          | -                                          | -                                                     |
| full suite | `.\.venv\Scripts\python.exe -m pytest -q`  | exit 0, `119 passed` at baseline; grows as phases add tests |

## Phase notes

### P1: grading_honesty

- **For other phases:** introduces a **fourth grade `Unscoreable`** and a new
  `UNSCOREABLE` sentinel verdict on `EqResult.verdict` (set by
  `compare_url_content`, not the LLM judge — the judge stays strictly TRUE/FALSE).
  Adds `fail_kind` to `DownloadResult` (`"html"` distinguishes a landing page
  from a 404/network failure). `grade_item` now also grades a **blank** inferred
  value as `Unknown` (was: only the literal `"UNKNOWN"`). Any Hit-rate math must
  **exclude `Unscoreable`** from the denominator (DECISIONS G2).
- **Notes:** Done. `fail_kind` ("" / "template" / "html" / "network" /
  "http_error") added to `DownloadResult`; `compare_url_content` returns
  `UNSCOREABLE`/`gt_not_a_file` only when GT is HTML and the inferred file
  already downloaded OK; `grade_item` grades blank-or-`"UNKNOWN"` inferred as
  `Unknown` and `UNSCOREABLE` as `Unscoreable`. ADR 0006 + `CONTEXT.md`
  written. 122 passed (119 + 3 new). Fresh-context review: spec conformance
  full pass, no correctness issues, no over-engineering findings beyond
  doc-mandated items (see phase doc Outcome).
- **Incoming comments:**

### P2: nuget_nuspec_fallback

- **For other phases:** adds `nuget_candidates(purl)` to `download.py` and wires
  it into `fetch_license_file` as a fallback (mirrors the npm path). It only ever
  produces a **downloadable LICENSE file** for the URL field; it **never invents
  a URL** from an SPDX id. When only an SPDX expression or a legacy EULA
  `licenseUrl` exists, no file is produced → the URL stays empty → P1's
  blank→Unknown grades it `Unknown`.
- **Notes:** Done. `nuget_candidates` fetches the flat-container nuspec, matches
  `<repository url>` by local XML tag name (namespace-agnostic), and derives
  `raw.githubusercontent.com/{owner}/{repo}/HEAD/{filename}` candidates; fails
  closed to `[]` on any fetch/parse issue or missing repo (never fabricates from
  SPDX). Wired into `fetch_license_file` as a fallback after the npm loop.
  HEAD-ref shortcut marked with the required `ponytail:` comment. 126 passed
  (122 + 4 new). Fresh-context review: spec conformance, failure-mode handling,
  and anti-goals all PASS; no over-engineering findings. Non-blocking note: the
  owner/repo extraction doesn't check the host, so a non-GitHub `<repository
  url>` (GitLab, Bitbucket, Azure DevOps) builds a raw.githubusercontent.com URL
  that will just 404 rather than returning `[]` early — harmless (no crash, no
  fabrication) but narrower than DECISIONS.md branch E's "repo's raw host"
  phrasing; worth revisiting if non-GitHub NuGet repos turn out to matter.
- **Incoming comments:**

### P3: copyright_honesty

- **For other phases:** `resolve_copyright` gains a **reject-only** guard: a
  small denylist of known stray/generic upstream holders (e.g. "The Go Authors")
  causes that candidate to be dropped and the chain to fall through to `UNKNOWN`,
  never emitting the wrong holder. The guard is **asymmetric** — it never
  requires the holder to match the package/repo owner. Also tightens the judge
  copyright prompt (small year tolerance; directional same-class "and others").
- **Notes:**
- **Incoming comments:**

### P4: offline_rescore_signoff

- **For other phases:** none — terminal phase. Extends
  `ad_hoc_scripts/analysis/rescore.py` to re-score the frozen run by **importing
  the real production functions** from P1–P3 (plus bounded live HTTP probes for
  GT content-type and NuGet fallbacks), writes a results doc to `docs/analysis/`,
  and migrates the accepted residual risks (DECISIONS branch I, #2–#5) to
  `docs/BACKLOG.md`. Requires P1, P2, P3 `done`.
- **Notes:**
- **Incoming comments:**

## On completion

Only after every phase shows `done` in the table above, in this order:

1. Graduate durable decisions out of the plan: anything in a Phase-notes
   block or a phase doc that a future maintainer must know goes to an ADR
   (invoke the `domain-modeling` skill; if unavailable, a dated note in the repo's docs).
   Note: P1 already writes the `Unscoreable` ADR (0006) and `CONTEXT.md` update
   inline — check nothing else durable remains unrecorded.
2. Stamp the top of this file: `COMPLETED {YYYY-MM-DD} — historical record,
   not current truth`.
3. Move the whole plan directory to `docs/plans/archive/fact-grade-tranche/`.

Stale plan docs poison future agents — archive, don't keep.
