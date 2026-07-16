---
name: run-and-test
description: >-
  Authoritative Windows/PowerShell commands for testing and running the SBOM
  Enricher: repo venv, pytest, config-driven enrichment, runtime reports, and
  required Claude CLI/Azure credentials. Use whenever asked to run pytest or
  tests, verify/validate changes, reproduce a failure or run, execute an
  enrichment, set up .venv, generate a report, or troubleshoot preflight/auth.
---

# Running & Testing the SBOM Enricher

Windows / PowerShell project. The interpreter is the in-repo venv at
`.venv\Scripts\python.exe`; prefer it over a bare `python`.

## Test suite (offline, safe, default)

`tests/conftest.py` puts `src/` on the path and autouse-mocks `preflight`.
Individual tests monkeypatch Claude/Azure/HTTP — the suite does not call live
providers when tests are written correctly. Go-to check after any change:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: exit 0. Baseline on this repo: **141 passed** (~60–90s). Useful
variants:

```powershell
# one file
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -q
# one test, verbose
.\.venv\Scripts\python.exe -m pytest tests/test_download.py::test_name -v
```

There is no pytest config file — tests are discovered from `tests/` and rely on
the `conftest.py` path insert, so run from the repo root.

## Environment setup (only if the venv is missing/stale)

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pytest
```

`requirements.txt` uses `openai`, `azure-identity`, `requests`. It also pins
`azure-ai-projects` and `pypdf` — not imported by current `src/` (legacy pins;
safe to install). Pytest is not listed there; install it separately in a fresh
venv.

## Live enrichment run

`src/main.py` uses bare imports (`from config import ...`), so run the script by
path — Python puts `src/` on `sys.path` automatically. It takes an optional
config path; default is `configs/default.json` (currently `GT_220.csv`, 20
workers, `cache_write: caches`).

```powershell
# default config
.\.venv\Scripts\python.exe src\main.py
# explicit config
.\.venv\Scripts\python.exe src\main.py configs\default.json
```

Output is a new run dir printed to stdout (progress/logs go to stderr). See the
`architecture-overview` skill for the run-dir layout.

### A run needs live credentials (tests do not)

`preflight()` fail-fasts before any work unless both are reachable:

- **Claude CLI** — the `claude` executable must be on PATH and authenticated
  (inference + preflight shell out to it).
- **Azure AD** — `DefaultAzureCredential` must resolve a token for scope
  `https://cognitiveservices.azure.com/.default` (e.g. `az login`). Deployment
  `gpt-4.1-limitless` and endpoint live in `gpt41_client.py`.

If you only need to validate code, run the test suite — preflight is mocked
there and provider calls are faked per test.

## Runtime report

Every successful enrichment automatically writes `runtime_report.html`.
Regenerate or open a report for an existing run with:

```powershell
.\.venv\Scripts\python.exe src\runtime_report.py <run_dir>
.\.venv\Scripts\python.exe src\runtime_report.py <run_dir> --out report.html --open
```

### Config fields (`configs/default.json`)

| Field | Meaning |
|-------|---------|
| `input_file_path` | Input CSV (needs `component_name`, `purl`; GT columns enable audit mode) |
| `output_base_path` | Where run dirs are written (default `runs/`) |
| `run_name` | Optional label, or `null` |
| `model` | One of `config.MODEL_CHOICES` (e.g. `claude-opus-4-8`) |
| `workers` | Concurrency, int in `[1, 30]` |
| `cache_read` / `cache_write` | Cache dirs, or `null` |

Relative paths resolve against the repo root. For a cheap cache-backed smoke
run, point `input_file_path` at a tiny CSV and `cache_read` at a populated
cache. Startup preflight still requires both live credentials; after it passes,
cache hits skip enrichment LLM calls. In audit mode, cache hits still run
equality (URL downloads + possible GPT judges).
