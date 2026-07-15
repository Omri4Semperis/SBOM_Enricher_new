---
name: architecture-overview
description: >-
  High-level map of the SBOM Enricher codebase — the enrichment pipeline, the
  module-to-responsibility layout under src/, the per-run output artifacts, and
  audit mode. Use as a fast orientation accelerator when starting work on this
  project, locating which module owns a concern, or reasoning about data flow.
  This is a map, not a deep dive — read the cited source file for details.
---

# SBOM Enricher — Architecture Overview

An orientation accelerator, not a spec. Use it to find the right module fast,
then read that file. For domain vocabulary see `docs/CONTEXT.md`; for locked
decisions see `docs/DECISIONS.md` and `docs/adr/`.

## What it does

Reads an input CSV of software components (`component_name`, `purl`), and for
each one infers three **enrichment fields** — license name, a downloadable
license-file URL (plus the downloaded file), and the copyright statement — all
fetched online. If the input carries ground-truth columns, it also audits the
enrichment against them.

## Two LLM providers

- **Claude CLI** (`claude` subprocess) — license-name + license-URL inference.
- **Azure OpenAI GPT-4.1** (`AsyncAzureOpenAI`, AD token) — copyright
  extraction and equality judging.

Both are reached through the locked retry policy in `retry.py`
(transient/parse/hard classification).

## Pipeline flow (one component)

`process_component` in `src/pipeline.py` is the spine:

1. **Cache check** (`cache.py`) — all-or-nothing hit by `component_name`
   short-circuits everything and returns immediately.
2. **License inference** (`claude_client.py`) — Claude returns
   `{license_name, license_code_url, reasoning}`.
3. **License download** (`download.py`) — rewrite viewer→raw URLs, reject
   HTML/templates, fall back to npm/unpkg candidates from the purl.
4. **Copyright extraction** (`copyright.py`) — GPT-4.1 reads the *downloaded
   file only* (ADR 0003); placeholders → UNKNOWN.
5. **Cache write** (`cache.py`) — only on full success (all three fields known).
6. **Equality** (`equality.py`, audit mode only) — see below.

Every step appends a human-readable line to the component's **Story**
(`per_component/{slug}/story.txt`). Timings/reasons are later parsed back out
of the Story by `summary.py` / `results_csv.py`.

## Concurrency & entry

- `src/main.py` — CLI entry: load config → `preflight` → build run dir →
  run workers → write `score.csv` + `summary.json`.
- `run_workers` in `pipeline.py` — bounded `asyncio.Semaphore(workers)` pool;
  results streamed to the CSV writers via `as_completed`.
- `preflight.py` — fail-fast connectivity probe of Claude + Azure before any
  work starts (mocked in tests).

## Module map (`src/`)

| Module | Responsibility |
|--------|----------------|
| `main.py` | CLI entry, orchestration, output writing |
| `config.py` | Load/validate `configs/*.json` → frozen `Config`; `REPO_ROOT`, `MODEL_CHOICES` |
| `input_csv.py` | Parse input CSV → `Component`; slugs, dedupe, passthrough columns |
| `pipeline.py` | `ComponentResult`, `process_component`, `apply_equality`, `run_workers` |
| `claude_client.py` | Claude CLI license inference (subprocess + JSON parse) |
| `gpt41_client.py` | Async Azure GPT-4.1 wrapper (`complete_json`) |
| `download.py` | License-file fetch: URL rewrite, HTML reject, npm fallback |
| `copyright.py` | File-only copyright extraction via GPT-4.1 |
| `equality.py` | Audit equality ladders (identical → normalized → LLM judge) |
| `scoring.py` | Grade Hit/Mismatch/Unknown; tally `score.csv` |
| `retry.py` | Locked async retry/backoff policy |
| `prompts.py` | All prompt/schema builders |
| `pricing.py` | Model price table + cost math (source-only constants) |
| `run_dir.py` | Create per-run output tree; name/short-model helpers |
| `results_csv.py` | Stream `results_*.csv` + `results_*_extended.csv` |
| `summary.py` | Build/write `summary.json`; parse Story timings/reasons |
| `progress.py` | Live stderr progress bar + ETA |

## Audit mode

Active only when the input has one or more ground-truth columns
(`license_name` / `license_code_url` / `copyright`), detected by
`detect_gt_columns`. When on: `apply_equality` fills `is_eq_*` verdicts,
`grade_row` assigns Hit/Mismatch/Unknown, and `write_score_csv` emits
`score.csv`. Equality uses a cheap ladder — exact match, then normalized match,
then a GPT-4.1 judge (ADR 0002: URLs compared by downloaded content).

## Per-run output tree

Under `output_base_path/` (default `runs/`), a dir named
`{timestamp}_{modelShort}_{n}/`:

```
input/            copy of input CSV + config.json snapshot
licenses/         downloaded license files, flat {slug}.ext
per_component/{slug}/  meta.json + story.txt (+ license copy)
results_{Model}_{n}.csv           main output (triplet columns)
results_{Model}_{n}_extended.csv  + raw/cost/cache/timing detail
score.csv         audit tally (audit mode only)
summary.json      run-level aggregates (timings, cost buckets)
```

## Cross-cutting conventions

- **Fail closed per component**: any component's error yields UNKNOWN fields,
  never crashes the run.
- **UNKNOWN vs empty cost**: missing cost is the marker `"unknown"`, never `0`
  (`pricing.UNKNOWN_COST`). Cost capture is partially stubbed — see the
  `docs/plans/cost-and-copyright-observability/` plan.
- **Cache is all-or-nothing**: only fully-successful enrichments are cached, and
  a cached reuse contributes zero Run Cost (ADR 0001).
- **Story is the source of truth** for post-hoc timings/reasons; the CSV/summary
  writers re-parse it rather than threading data through `ComponentResult`.
