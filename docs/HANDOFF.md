# HANDOFF — Write implementation plan for 2026-07-19 grilled requirements

- Objective: Produce an implementation plan (via `complex-plan-create`) for the
  five grilled requirements. Decisions are already signed off — do not re-grill.
- Repo: C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve sbom-enricher agent/SBOM_Enricher_new
- Branch: master
- HEAD: 5bbb5c8
- Dirty: 5 uncommitted paths (docs only: CONTEXT.md, DECISIONS.md, ADRs 0011–0013)

## Files changed
Base: working tree vs HEAD (uncommitted grilling docs; not yet committed).

- M docs/CONTEXT.md — glossary: Component, Enriched Output CSV, Inferred License Code URL, Equality→0013
- M docs/DECISIONS.md — full A–F grilling recap dated 2026-07-19
- A docs/adr/0011-duplicate-component-conflict-reject.md
- A docs/adr/0012-enriched-output-csv-replace-keep.md
- A docs/adr/0013-audit-reuse-inferred-license-file.md

## Commands run + results
- Grilling + domain-modeling only; no builds/tests this session.

## Test status
not run

## Assumptions
1. Docs above are complete enough to plan; no need to re-open design questions
   unless a plan phase discovers a contradiction with code.
2. C (project layout) and E (prompt-only URL quality) have no ADRs by design —
   they live only in DECISIONS.md / CONTEXT (URL meaning).

## Open questions
None — grilling signed off; ADRs accepted.

## Chat residue (not elsewhere, or easy to miss)
1. **Do not re-grill.** User confirmed docs are the source of truth for planning.
2. **"Parsing error"** appeared in the original ask; codebase has no such
   sentinel. "Bad" enrichment value = empty/whitespace, `UNKNOWN`, or component
   errored (DECISIONS B3). Do not invent a Parsing-error path.
3. **Colleague check (answered):** same `component_name` is enriched once per
   run (ADR 0011 / A5); cross-run cache still applies (ADR 0001).
4. **Likely code touchpoints** (for the plan, not re-decided):
   - `src/input_csv.py` — today rejects duplicate `component_name`
   - `src/equality.py` — `__eq_inf` / `__eq_gt` downloads
   - `src/download.py` — `_write_license` flat `licenses/{slug}.ext`
   - `src/results_csv.py` / `src/main.py` — CSV writers; new enriched CSV post-run
   - `src/prompts.py` — `license_prompt` (E)
   - `src/cache.py` — `restore_license_file` must obey project layout (F2)

## Next action
Using `.cursor/skills/complex-plan-create/SKILL.md`, create a multi-phase
implementation plan whose sole requirements sources are:
`docs/DECISIONS.md` (section 2026-07-19), `docs/CONTEXT.md`,
`docs/adr/0011-duplicate-component-conflict-reject.md`,
`docs/adr/0012-enriched-output-csv-replace-keep.md`,
`docs/adr/0013-audit-reuse-inferred-license-file.md`,
plus this HANDOFF's "Chat residue" and the code touchpoints listed there.
Orient with `.cursor/skills/architecture-overview/SKILL.md` if needed. Do not
re-open signed-off decisions; escalate only true contradictions with code.
