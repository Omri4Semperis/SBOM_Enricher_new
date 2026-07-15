# HANDOFF — Build the implementation plan for the grilled suggestions

Consumed: 2026-07-15 (plan created at `docs/plans/fact-grade-tranche/`; P1 done, now executing P2)

- Objective: Turn the signed-off grilling decisions in `docs/DECISIONS.md` into a
  multi-phase implementation plan (via `complex-plan-create`), then implement.
  The grilling is complete; no design questions remain open.
- Repo: `C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve sbom-enricher agent/SBOM_Enricher_new`
- Branch: `master`
- HEAD: `30a06db`
- Dirty: 6 untracked paths (no commits this session)

## Focus

Grilling of the post-run top-3 suggestions is DONE and signed off. Next session
builds the plan; do not start coding before the plan exists.

## What was decided (read these, not memory)

- `docs/DECISIONS.md` — all committed decisions (branches A–I + H.1) and the
  recap. This is the single source of truth for the plan.
- `docs/DEFERRED.md` — deferred/rejected items with triggers + owners.
- `docs/analysis/2026-07-15_run-144424_root-cause-analysis.md` — evidence base.
- `docs/archive/SUGGESTIONS_2026-07-15_run-144424.md` — the original (archived)
  plan that was grilled.

Committed tranche (fact-grade first): (1) `Unscoreable` URL grade for GT-not-a-file
via HTML content-type; (2) blank inference → Unknown; (3) NuGet nuspec fallback
(repo LICENSE; SPDX informs name only); (4) narrow reject-only copyright denylist
guard; (5) judge prompt-tightening (small year tolerance; directional same-class
"and others"). Contract: `UNSCOREABLE` sentinel verdict (judge stays TRUE/FALSE).

## Files changed

Base: `HEAD` (`30a06db`). No commits — all untracked:

- `docs/DECISIONS.md` — grilling decisions + recap (new)
- `docs/DEFERRED.md` — deferred concepts (new)
- `docs/archive/HANDOFF_2026-07-15_grill-suggestions.md` — prior handoff, consumed
- `docs/archive/SUGGESTIONS_2026-07-15_run-144424.md` — archived source plan
- `docs/analysis/`, `ad_hoc_scripts/` — analysis doc + reproduction scripts/output

## Commands run + results

- `git branch/rev-parse/status` → branch `master`, HEAD `30a06db`, 6 untracked.

## Test status

not run (no code changed this session — docs only)

## Assumptions

1. Next session runs `complex-plan-create` on `docs/DECISIONS.md`, not ad-hoc coding.
2. Implementation order respects the sequencing note in G3 (NuGet fallback lands
   before "empty→Unknown" is meaningful).
3. Run dir `runs/20260715_144424_ClaudeOpu-4-8_380/` stays on disk (offline
   re-score evidence).

## Open questions

None — grilling resolved all design branches. (Two durable-doc follow-ups belong
in the plan: update `CONTEXT.md` Scoring Outcome + Equality terms, and add an ADR
for the `Unscoreable` grade.)

## Next action

Run `complex-plan-create` to produce a phased implementation plan under
`docs/plans/` from `docs/DECISIONS.md` (committed tranche + H validation +
CONTEXT/ADR updates). Do not implement until the plan exists.
