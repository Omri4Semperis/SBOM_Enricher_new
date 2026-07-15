# Plan: fact-grade-review-fixes

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

Clear every finding in the fact-grade tranche review
(`docs/full-review_fact-grade-tranche.md`) so the tranche can be signed off:
one blocker (B1), four should-fixes (S1–S4), one nit (N1). The fixes are
surgical — a host gate, an async offload, a version normalizer, an
association-aware guard, a clearer log line, and an honesty correction to one
analysis doc. Two decisions are durable enough to record as ADRs. When all
three phases are `done`, the review's verdict of **reject** is answered.

## Context

SBOM Enricher enriches a CSV of components with license + copyright fetched
online. Windows/PowerShell repo; the interpreter is the in-repo venv at
`.venv\Scripts\python.exe`. The offline test suite mocks all live providers,
so it is the go-to check after any change. Run everything from the repo root.

The six findings, verbatim intent from the grilling session (see the review
doc for the reviewer's wording):

- **B1 (blocker)** `src/download.py` `nuget_candidates` — a non-GitHub
  `<repository url>` is reduced to `owner/repo` and rewritten to
  `raw.githubusercontent.com`, silently attributing an unrelated GitHub repo's
  license. Gate raw-URL construction on a recognized GitHub host; return `[]`
  otherwise.
- **S1** `src/copyright.py` `_is_stray_holder` — a holder-only denylist wrongly
  rejects legitimate Go/Android packages. Make it association-aware (pass
  `purl`/`lib_name`; reject a stray holder only when the package is not of that
  family). **ADR required** (0007).
- **S2** `src/download.py` — the synchronous nuspec `requests.get` runs inside
  the asyncio loop, freezing every worker. Offload via
  `await asyncio.to_thread(nuget_candidates, purl)`.
- **S3** `src/download.py` — the flat-container endpoint needs a
  NuGet-normalized, lowercased version, but the purl version is used verbatim.
  Normalize it.
- **S4** `ad_hoc_scripts/analysis/rescore.py` — blanking a rejected copyright
  and grading it `Unknown` does not reproduce production (which continues
  through npm + web fallbacks). Report only the guard-trigger count, and
  correct the false "20 → Unknown" claim in the generated analysis doc.
- **N1 (nit)** `src/download.py` — a valid `pkg:nuget/` purl that yields no
  candidates is logged as "non-nuget purl", hiding the real failure.
  Distinguish the two cases.

Findings group by file, so phases are: P1 owns all of `src/download.py`
(B1+S2+S3+N1), P2 owns the copyright guard (S1), P3 owns the offline re-score
honesty (S4). P1 and P2 are independent. P3 depends on P2 because it imports
and calls `copyright._is_stray_holder`, whose signature P2 changes.

## Phases

| Phase                                                          | Purpose                                            | Depends on | Status  | Baseline | Updated |
| -                                                              | -                                                  | -          | -       | -        | -       |
| [P1: harden_download_path](./P1_harden_download_path.md)       | B1+S2+S3+N1: gate host, offload, normalize, log    | -          | done | 1d99bae | 2026-07-16 |
| [P2: association_aware_holder](./P2_association_aware_holder.md) | S1: association-aware stray-holder guard + ADR 0007 | -          | pending |          |         |
| [P3: honest_rescore_and_doc](./P3_honest_rescore_and_doc.md)   | S4: guard-count-only re-score + doc correction     | P2         | pending |          |         |

## Test commands

| Purpose             | Command                                                        | Expected                       |
| -                   | -                                                              | -                              |
| full suite          | `.\.venv\Scripts\python.exe -m pytest -q`                      | exit 0, ≥130 passed            |
| one file (download) | `.\.venv\Scripts\python.exe -m pytest tests/test_download.py -q` | exit 0, all passed             |
| one file (copyright)| `.\.venv\Scripts\python.exe -m pytest tests/test_copyright.py -q` | exit 0, all passed             |
| compile a script    | `.\.venv\Scripts\python.exe -m py_compile <path>`              | exit 0, no output              |

Baseline captured at plan creation: **130 passed in ~12s**. New tests only add
to this; the count must never drop.

## Phase notes

### P1: harden_download_path

- **For other phases:** `nuget_candidates(purl)` keeps its signature
  (`str -> list[str]`) — only its internals change. P3 (which imports it) is
  unaffected by P1. After P1, `nuget_candidates` returns `[]` for a nuspec whose
  `<repository url>` is not on `github.com`/`www.github.com`.
- **Notes:** Done. B1/S2/S3/N1 fixed in `src/download.py` (one commit per
  task), ADR 0008 recorded. Fresh review (subagent) verdict: PASS, no
  doc-compliance or over-engineering findings. Suite: 134 passed (130
  baseline + 4 new), `test_download.py`: 26 passed. `nuget_candidates`
  signature confirmed unchanged — P3 unaffected.
- **Incoming comments:**

### P2: association_aware_holder

- **For other phases:** `_is_stray_holder` changes signature from
  `_is_stray_holder(text)` to accept the package context (`purl`, `lib_name`).
  Any caller passing only `text` will break. The in-repo callers are
  `src/copyright.py` (P2 fixes these) and `ad_hoc_scripts/analysis/rescore.py`
  (P3 must update its call — see Incoming comment below).
- **Notes:**
- **Incoming comments:**
  - {seed} [from planner] P3: after P2, update `rescore.py`'s
    `_is_stray_holder(inferred)` call to the new signature; see P2's Outcome for
    the exact signature.

### P3: honest_rescore_and_doc

- **For other phases:** terminal phase; exposes nothing.
- **Notes:**
- **Incoming comments:**

## On completion

Only after every phase shows `done` in the table above, in this order:

1. Graduate durable decisions out of the plan: anything in a Phase-notes
   block or a phase doc that a future maintainer must know goes to an ADR
   (invoke the `domain-modeling` skill; if unavailable, a dated note in the repo's docs).
   Both ADRs (0007 for S1, 0008 for B1) are authored inside their phases, so
   this step is only a final check that nothing else durable was left behind.
2. Stamp the top of this file: `COMPLETED {YYYY-MM-DD} — historical record,
   not current truth`.
3. Move the whole plan directory to `docs/plans/archive/fact-grade-review-fixes/`.

Stale plan docs poison future agents — archive, don't keep.
