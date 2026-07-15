# Full review — docs/plans/archive/v2-enricher/

Reviewed: the archived 8-phase plan (`PLAN.md` + `P1`–`P8`), 9 files, 1,896
lines. This is a completed, archived planning artifact ("historical record,
not current truth"), not live code — so the lens is record quality:
internal consistency, honesty about what shipped, and whether the durable
debt survived archival. No live `git diff` exists (HEAD is post-archive);
reviewed the named directory per the user's request.

## Executive summary

LGTM as a historical record. This is a genuinely well-run plan: eight
self-contained phase docs, a live `PLAN.md` that chains cleanly
(tests grow 6→15→26→43→50→58→78→94, each phase's baseline/`done` recorded),
locked decisions referenced instead of re-litigated, and every deviation
logged in the phase it happened in. Its strongest move is debt handling —
the cost/token-capture gap discovered late (P8) is flagged via **Incoming
comments** in P3/P5/P6/P7 *and* graduated to `BACKLOG #6`, so the debt
outlives the archived plan (which the plan itself says future agents must
not trust). The one substantive caveat: the plan is stamped COMPLETED while
P8's flagship `summary.json`/extended-CSV **cost buckets ship non-functional**
(`unknown` costs, `saved_by_cache_usd=0.0` always). That was foreseen and
parked, not an oversight — but "COMPLETED" overstates functional completeness
of the cost-reporting feature, and that caveat lives only in the archive +
backlog, not next to the output it describes.

## Blockers

none — archived documentation; no correctness/security/data-loss surface.

## Should-fix

- `docs/BACKLOG.md:15` — the cost-reporting caveat (summary.json costs are
  placeholder `unknown`, `saved_by_cache_usd` always `0.0`) lives only in the
  archived plan's Incoming comments and BACKLOG #6. A reader of a real
  `summary.json` / extended CSV has no signal the cost columns are unpopulated.
  Fix: put a one-line "costs are placeholder until BACKLOG #6" note where the
  output is documented/produced (a live doc or the summary writer), not only in
  the archive. (Out of the archived dir, but it's the concrete gap the archive
  exposes.)
- `docs/plans/archive/v2-enricher/PLAN.md:56` — the phase-table `Baseline`
  hashes don't reconcile with the per-phase `Outcome` HEADs (e.g. P2 Outcome
  HEAD `bd73882`, but P3's baseline is `234411c`, not `bd73882`). For a record
  whose whole point is forensic reconstructability, the hash chain has gaps —
  someone bisecting from these will be misled. Either the outcomes were amended
  post-hoc or the baselines were backfilled inconsistently; a one-line note
  saying which would restore trust.

## Nits

- `docs/plans/archive/v2-enricher/P4_license_download.md:19` (also P5/P6/P7/P8)
  — Entry-criteria checkboxes stay `[ ]` unchecked in completed phases while
  P1/P2/P3 use `[x]`. In a `done` phase, unticked entry gates read as
  "never satisfied". Cosmetic, but inconsistent hygiene across the set.
- `docs/plans/archive/v2-enricher/P3_license_inference.md:32` — 218-char line
  (the Claude CLI call shape). The only genuinely long line; the rest of the
  long-line hits are `PLAN.md` phase-table rows (183–184 chars), which are
  benign markdown tables. Author's call.
- Cross-doc boilerplate: the "Your workspace" preamble, `Rollback`,
  `If blocked`, and `On completion` blocks are near-identical across all eight
  docs (~40 lines/doc). This is defensible — the execution model is one fresh
  session per phase, so each doc must stand alone — but it's the one place the
  plan pays a real duplication cost. Not a finding given the design intent.

## Census

- `file_lengths` (--all): clean, no breach — longest `PLAN.md` 282 lines
  (< 400 threshold). All 9 docs 174–282.
- `long_lines` (--max 160): breach (exit 1) — 1 real hit (`P3:32`, 218);
  remaining 10 hits are `PLAN.md` table rows (182–184). Benign for markdown.
- `todo_scan`: clean — zero TODO/FIXME/HACK/XXX markers.
- `ponytail_debt`, `risky_patterns`, `test_presence_ratio`: not run —
  markdown-only target (debt scanner skips `.md`; the others are code lenses).
- Cross-check vs repo: all 18 `src/*.py` modules named in the phase Touch
  lists exist; `BACKLOG #6` matches the four Incoming-comment references;
  HEAD is `19750be` (post-archive), so no reviewable working diff.

Verdict: approve
