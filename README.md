# SBOM Enricher

> **Built for agents (and humans).** This project is designed to be ideal for
> agentic interaction: a coding agent can orient, run, test, and extend it with
> minimal friction thanks to the docs in `docs/` and the skills under
> `.cursor/skills/` (mirrored for Copilot in `.github/skills/`). Humans can
> absolutely use, run, and develop it too — but an agent will do a great job
> driving it.

Enriches a CSV of software components with their **license name**, a
downloadable **LICENSE-file URL** (plus the downloaded file), and the
**copyright statement** found in that file — all fetched online. When the input
carries ground-truth columns, it also **audits** the enrichment against them and
scores accuracy.

## What it does

For each input row (`component_name`, `purl`) the pipeline:

1. Checks an optional cache (all-or-nothing by `component_name`).
2. Infers the license name and a license-file URL (Claude CLI).
3. Downloads and validates the license file (with npm / NuGet fallbacks).
4. Extracts the copyright (GPT-4.1 on the file → registry author → web).
5. In audit mode, compares each field to ground truth and grades it.

Every run writes a self-contained HTML report, per-component narratives, a
machine-readable event log, and (in audit mode) a score tally.

## Requirements

- Windows / PowerShell.
- Python 3 (an in-repo virtual env at `.venv`).
- **Claude CLI** — the `claude` executable on `PATH`, authenticated.
- **Azure OpenAI** — `DefaultAzureCredential` able to get a token for
  `https://cognitiveservices.azure.com/.default` (e.g. `az login`).

A live run needs both credentials; the test suite does not (providers are
mocked).

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

## Run an enrichment

```powershell
# uses configs/default.json
.\.venv\Scripts\python.exe src\main.py

# or an explicit config
.\.venv\Scripts\python.exe src\main.py configs\default.json
```

The run directory is printed to stdout; progress/logs go to stderr.

### Config (`configs/default.json`)

| Field | Meaning |
|-------|---------|
| `input_file_path` | Input CSV (needs `component_name`, `purl`; ground-truth columns enable audit mode) |
| `output_base_path` | Where run dirs are written (default `runs/`) |
| `run_name` | Optional label, or `null` |
| `model` | One of `config.MODEL_CHOICES` (default `claude-sonnet-5`) |
| `workers` | Concurrency, int in `[1, 30]` |
| `cache_read` / `cache_write` | Cache dirs, or `null` |

## Output (per run)

Under `runs/{timestamp}_{model}_{n}/`:

- `results_*.csv` / `results_*_extended.csv` — the enriched output.
- `runtime_report.html` — human-readable timing + accuracy report.
- `per_component/{slug}/` — `story.txt` narrative + `meta.json` (+ license copy).
- `licenses/` — downloaded license files.
- `events.jsonl` — machine-readable event log.
- `score.csv` + `summary.json` — audit tally and run aggregates.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Offline and safe (~157 tests). Run from the repo root.

## Reports for an existing run

```powershell
.\.venv\Scripts\python.exe src\runtime_report.py <run_dir> --open
.\.venv\Scripts\python.exe src\event_report.py <run_dir>
```

## Learn more

- `docs/CONTEXT.md` — domain vocabulary.
- `docs/adr/` — durable architecture decisions.
- `.cursor/skills/architecture-overview` — codebase map.
- `.cursor/skills/run-and-test` — authoritative run/test commands.
- `AGENTS.md` — conventions for agents working in this repo.
