# HANDOFF — grilling to align terms + goals for SBOM Enricher v2

- Objective: Grill Omri to lock terminology + goals for a rewrite of the SBOM
  enricher, capturing every decision in living docs (`docs/DECISIONS.md` +
  `docs/CONTEXT.md`) that will later drive a complex-plan creation. Not
  building code yet.
- Repo: C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve sbom-enricher agent/SBOM_Enricher_new
- Branch: master
- HEAD: 723054b
- Dirty: 0 uncommitted paths (working tree clean; last commit pushed to origin/master)

## Files changed

Base = b6ccb7d (previous handoff commit). This session's commit 723054b:

- `M docs/DECISIONS.md` — appended LOCKED decisions for equality-judge schema,
  model fixed-vs-configurable, results.csv column order + CSV encoding, scope
  boundaries, and security/credentials + preflight. **Live source of truth —
  read this first.**
- `R CONTEXT.md → docs/CONTEXT.md` — glossary relocated to `docs/`.
- `M .cursor/skills/domain-modeling/{SKILL,CONTEXT-FORMAT}.md` — updated the
  domain-modeling skill to place the glossary under `docs/`.

## Commands run + results

- git add/commit/push → commit 723054b pushed cleanly (b6ccb7d..723054b).
- No builds/tests/migrations — documentation-only session.

## Test status

Not run (no code yet).

## Branches resolved this session (detail in `docs/DECISIONS.md`)

Advanced Q11→Q17 and LOCKED:

- **LLM contracts (branch DONE):** equality-judge output
  `{ verdict: "TRUE"|"FALSE", reasoning }` — one uniform schema across all
  three comparison kinds; TRUE/FALSE (not YES/NO) for clean Excel filtering.
  Model roles: Claude is the single configurable `model` knob (benchmarked for
  cost/time/accuracy); GPT-4.1 is fixed/hard-coded.
- **Input / output contract (branch DONE):** main `results.csv` column order is
  per-item triplets — `component_name, purl,` then
  `{gt}, inferred_{item}, is_eq_{item}` for license_name / license_code_url /
  copyright; degrades cleanly when GT columns are absent; extra input columns
  preserved at the end. CSV writer = stdlib `csv.DictWriter`, `utf-8-sig`
  (BOM for Excel), `newline=""`; no pandas.
- **Scope boundaries (branch DONE):** empty/malformed `purl` cell → row
  continues (degraded, likely UNKNOWN), not fail-fast; deterministic download
  fallback stays npm/unpkg-only; CSV-only input, one file per run.
- **Security / credentials (branch DONE):** no secrets in code/config; Azure via
  `DefaultAzureCredential`, Claude via local CLI session; hard-coded endpoints
  are non-secret. Startup connectivity preflight probes both providers and
  fails fast, but is itself retried ≥3 attempts with increasing *deterministic*
  backoff (e.g. 2s/4s/6s) so a transient blip doesn't kill a run.

## Assumptions

1. `results.csv` extra/unknown input columns are appended at the end in
   original order (recorded in DECISIONS.md; Omri hasn't objected).

## Open questions (grilling branches not yet resolved)

Only two branches remain (checklist authoritative in `docs/DECISIONS.md`):

1. **Open risks / deferred** — enumerate known risks + explicitly deferred
   levers (restore consistency judge, broaden deterministic fallback,
   circuit-breaker) with owners.
2. **Decision recording** — at close, write the grilling recap (one line per
   decision) for Omri's sign-off, then offer ADRs for durable choices via the
   `domain-modeling` skill.

Note: `docs/DECISIONS.md` still references the glossary as `CONTEXT.md` in a
couple of spots (line ~9, ~201); it now lives at `docs/CONTEXT.md`. Fix in
passing.

## Next action

Resume the grilling in the **Open risks / deferred** branch: ask Omri, one
question at a time with a recommended answer, to confirm the deferred-levers
list and any residual risks. Then run the grilling **Closing** (recap →
sign-off → offer ADRs). Keep the one-question-at-a-time cadence.
