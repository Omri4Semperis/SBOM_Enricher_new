# HANDOFF — incorporate the run-160137 accuracy review into the app

- Objective: Act on `docs/analysis/2026-07-16_run-160137_accuracy-review.md`.
  The reported hit-rates (license 83% / URL 74% / copyright 68%) understate
  real accuracy; turn its findings into (1) enricher fixes, (2) grader/report
  fixes, gated by (3) a reporting-policy decision. Analysis is complete; **no
  code or scoring changes have been made yet.**
- Repo: C:\Users\OmriNardiNiri\Documents\_Dev\2026-06-07 improve sbom-enricher agent\SBOM_Enricher_new
- Branch: master
- HEAD: d1fc84a
- Dirty: 2 uncommitted paths (this handoff + the analysis doc)

## Files changed

Base: HEAD (d1fc84a). All untracked, none committed.

- `docs/analysis/2026-07-16_run-160137_accuracy-review.md` — the analysis +
  improvement plan (sections A enricher / B measurement / C grilling).
- `docs/HANDOFF.md` — this file.

## Commands run + results

- Analysis only: parsed `runs/20260716_160137_ClaudeSon-5_220/`
  `results_*_extended.csv` (grades, GT-vs-inferred, judge reasons) + inspected
  downloaded license files; 3 targeted web checks. No pipeline/grader changes.

## Test status

not run (no code changed).

## Assumptions

1. GT can be wrong/ambiguous (source-repo license vs shipped-artifact EULA);
   the run's mismatches were sampled, not exhaustively re-classified.

## Open questions (for the grilling session — section C of the analysis)

1. "Correct" per field = source-repo license or shipped-artifact license?
2. Report accuracy-vs-GT or accuracy-vs-truth (accepting GT errors)?
3. Hit tiers: holder-match-but-year-differs = Hit / partial / miss?
4. How to surface un-gradeable-due-to-GT rows in the headline number.

## Next action

Run a `grilling` session on the section-C reporting-policy questions above,
then capture the outcome as an ADR under `docs/adr/` before touching
`scoring.py` / `runtime_report.py` (section B) or the enricher (section A).
