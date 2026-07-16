# HANDOFF — diagnose why run 380 costs ~600 worker-s/component (analysis only)

Consumed: 2026-07-16

- Objective: Explain the slow throughput of run `20260716_102127_ClaudeOpu-4-8_380`
  and name the single highest-leverage fix. Analysis only — no `src/` edits, no
  fix applied yet.
- Repo: C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve sbom-enricher agent/SBOM_Enricher_new
- Branch: master
- HEAD: 828a1d7
- Dirty: 10 uncommitted paths (mostly untracked run/cache artifacts, unrelated)

## Constraints (from the tasking user)

- Do NOT touch `runs/20260716_102127_ClaudeOpu-4-8_380` (live run), do NOT modify
  `src/`, do NOT kill any process. Evidence lives in the mid-run copy
  `runs/20260716_102127_ClaudeOpu-4-8_380 - Copy` (torn trailing rows discarded).

## Files changed (base = HEAD 828a1d7; all untracked, none committed)

- `docs/perf_analysis_20260716_run380.md` — the deliverable report (has a
  Correction section that supersedes the original conclusion).
- `ad_hoc_scripts/analysis/parse_run_latency.py` — per-stage latency + web/npm counts.
- `ad_hoc_scripts/analysis/concurrency_timeline.py` — sweep-line concurrency from mtimes.
- `ad_hoc_scripts/analysis/timeout_and_gptclient.py` — timeout-accuracy risk + GPT-path timing.
- `ad_hoc_scripts/analysis/runtime_report.py` — pre-existing, NOT mine (was untracked at session start).

## Commands run + results

- `python ad_hoc_scripts/analysis/parse_run_latency.py` → 221 clean CSV rows;
  license mean 199s, copyright mean 175s, total mean 396s; 0 license retries;
  copyright web-fallback 99/221.
- `python ad_hoc_scripts/analysis/concurrency_timeline.py` → mtimes preserved
  (span ~3900s); peak concurrency 30, avg 20.4.
- `python ad_hoc_scripts/analysis/timeout_and_gptclient.py` → Claude >300s calls
  are productive/correct; **GPT-4.1 copyright extract (file-only path) = 109s median**.

## Test status

Not run. This was analysis of an external run; no unit tests touched.

## Key findings (detail in the report)

1. ~600s is mostly INHERENT: two sequential Claude Opus calls/component
   (license ~199s + copyright web ~175s), same ladder/model as `knowledge/old_code`.
2. Rate-limit/429: REFUTED (0 retries). Semaphore reaches 30 (not misconfigured).
3. LEADING PATHOLOGY: GPT-4.1 copyright-extract runs ~109s median where the
   client (`timeout=60, max_retries=0`) caps a single success at ≤60s ⇒ it is
   timing out/retrying or starving. Suspect: `src/copyright.py` builds a fresh
   `Gpt41Client()` per call (blocking `DefaultAzureCredential`, no pool/token
   cache); old_code and the new equality path share one client.
4. Original "re-add 300s Claude timeout" idea is WRONG: finished data shows slow
   Claude calls are correct (license >360s: 4/4 correct); a 300s cap loses Hits.

## Assumptions

1. The `- Copy` dir's file mtimes reflect real write times (span ~3900s supports this).
2. `copyright_elapsed_s` on the file-only path is dominated by the GPT extract
   call (resolve_copyright returns right after a successful file extract).
3. `gpt-4.1-limitless` endpoint slowness/throttling at concurrency 30 is NOT yet
   ruled out as an alternative cause to the per-call-client theory.

## Open questions

1. Is the GPT slowness the per-call client (blocking AAD) or the endpoint
   throttling at 30 concurrent? Needs the confirmation below to decide.
2. Does the user want a fix applied after confirmation, or report only?

## Next action

Run the cheap confirmation before any `src/` change: instrument ONE GPT-4.1
copyright-extract to log its `with_retries` attempt count + per-attempt latency
(and count `APITimeoutError`), and separately time a `Gpt41Client()`
construction + first token fetch. If attempts>1 or construction takes seconds,
the per-call-client diagnosis holds → then propose sharing one client. (Respect
the no-`src/`-edit / no-touch-live-run constraints; use a throwaway script.)
