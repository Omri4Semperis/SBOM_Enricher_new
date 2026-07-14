# HANDOFF — grilling session to align terms + goals for SBOM Enricher v2

- Objective: Run a grilling session that aligns on terminology and goals for a
  rewrite of the SBOM enricher, capturing decisions in living docs that will
  later drive a complex-plan creation. Not building code yet.
- Repo: C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve sbom-enricher agent/SBOM_Enricher_new
- Branch: master
- HEAD: 0be26a1
- Dirty: 9 uncommitted paths (see below)

## Files changed

Base = HEAD (0be26a1); nothing committed this session.

- `?? CONTEXT.md` — domain glossary (domain-modeling format); seeded earlier.
- `?? docs/DECISIONS.md` — grilling working log: branch checklist + LOCKED
  decisions. **The live source of truth — read this first.**
- `?? docs/HANDOFF.md` — this file.
- `M configs/default.json` — pre-existing edit (field set matches locked schema).
- `M .cursor/skills/handoff/SKILL.md` — pre-existing edit, not from grilling.
- `D knowledge/claude_query.py`, `D knowledge/gpt-4-1_query.py` — pre-existing,
  renamed by user to `query_example_claude.py` / `query_example_gpt-4-1.py`.
- `?? knowledge/old_code/`, `?? knowledge/query_example_*.py` — reference
  material (inspiration only), pre-existing.

## Commands run + results

- git status/rev-parse/branch for this handoff → clean read, no writes.
- Read old reference code (`knowledge/old_code/src/{config,cache_store,run_config}.py`)
  to ground Config/ops recommendations.
- No builds/tests/migrations — documentation-only session.

## Test status

Not run (no code yet).

## Branches resolved this session (detail in `docs/DECISIONS.md`)

Since the last handoff, the grilling advanced from Q9 through Q10 and LOCKED:

- **Config / ops (branch DONE):**
  - Simplified cross-run cache: key = `component_name`; stores license name,
    url, copyright + downloaded file; only `cache_read`/`cache_write` path
    knobs (null/empty ⇒ skip silently, no prompt); no `force_*` flags.
    All-or-nothing hits; only fully-successful rows written (no `UNKNOWN`s).
  - One `workers` knob, one pool, per-component end-to-end pipeline.
  - `default.json` field set locked (on-disk key names kept as-is);
    `model` stays a fixed allow-list.
  - Keep old progress bar + add ETA.
- **Failure handling (branch DONE):**
  - Transient comms failures: retry 3 total; #1 fixed 2s, #2 random [3s, 8s]
    (jitter). No retry on 4xx. Parse failures: retry 2 total, fixed 1s. Values
    hard-coded, not config. Fail closed to `UNKNOWN`.
  - Startup/config failures fail-fast; per-component runtime failures continue
    (no circuit-breaker for v2).
- **LLM contracts (branch IN PROGRESS):**
  - License inference (Claude): `{license_name, license_code_url, reasoning}`,
    all always present; `UNKNOWN` sentinel; no confidence field. LOCKED.
  - Copyright extraction (GPT-4.1): input = downloaded LICENSE text only;
    output `{copyright, reasoning}` with `UNKNOWN` sentinel (option A,
    supersedes the earlier `found: bool`). LOCKED.

## Open questions (grilling branches not yet resolved)

Authoritative list + branch checklist live in `docs/DECISIONS.md`. Summary:

1. **LLM contracts (in flight):** equality-judge (GPT-4.1) JSON schema; confirm
   GPT-4.1 fixed vs configurable across all roles.
2. Input/output contract: exact `results.csv` column order + encoding.
3. Scope boundaries.
4. Security / credentials (Azure `DefaultAzureCredential`, Claude CLI auth).
5. Open risks / deferred.
6. Decision recording: offer ADRs for durable choices at session close.

## Next action

Resume the grilling in the **LLM contracts** branch: ask Omri for the
equality-judge (GPT-4.1) JSON schema and whether GPT-4.1 is fixed vs
configurable for all its roles. Record in `docs/DECISIONS.md`, then move to the
Input/output contract branch (results.csv column order + encoding). Keep the
grilling cadence: one question at a time, each with a recommended answer.

## Paste into the fresh session (fallback only)

    Read docs/HANDOFF.md at C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve sbom-enricher agent/SBOM_Enricher_new. Continue the grilling from "Next action" using the grilling skill.
    Attach: docs/DECISIONS.md, CONTEXT.md.
