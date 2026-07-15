# P4: offline_rescore_signoff

**Plan:** fact-grade-first tranche — make the audit measurement truthful without
gaming the headline number. This is the terminal sign-off phase; read `PLAN.md`'s
Goal and Context in full before starting.

**Your workspace.** This doc is writable: record decisions, dead ends, and
findings here during implementation. The other file you may edit is `PLAN.md`
(your table row, your Phase-notes block, and Incoming comments in other blocks).
Never edit another phase's `P*` doc. Status lives in `PLAN.md`'s table.

**Demo:** `python ad_hoc_scripts/analysis/rescore.py` prints (and writes) a table
of predicted grade movements over the frozen run — Mismatches becoming
`Unscoreable`/`Unknown`/`Hit` — computed by calling the **real** P1–P3 production
functions, and a results doc lands in `docs/analysis/`.

**Goal:** Provide the DECISIONS-H sign-off gate: an offline re-score of the frozen
run `runs/20260715_144424_ClaudeOpu-4-8_380/` that **imports the real production
functions** (never reimplements grade logic) plus **bounded live HTTP probes**
for the facts that need the network (GT content-type for `Unscoreable`; NuGet
fallback reachability). Confirm the movements match the root-cause predictions,
write the results to `docs/analysis/`, and migrate the accepted residual risks to
`docs/BACKLOG.md`. A full 380-row live re-run stays opt-in — this phase does not
require it.

## Entry criteria

Run each; all must hold before other work. If any fails, follow **If blocked**.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] P1, P2, P3 all show `done` in `PLAN.md`'s phase table
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0 (all phases' tests pass)
- [ ] `git status --porcelain` → empty (clean tree)
- [ ] `runs/20260715_144424_ClaudeOpu-4-8_380/results_ClaudeOpu-4-8_380_extended.csv` exists

## Context capsule

`ad_hoc_scripts/analysis/rescore.py` already exists and today re-scores the frozen
run with a *reimplemented* policy (its own `classify_url` / `classify_copyright`
heuristics over `eq_*_reason` strings). This phase replaces the reimplemented bits
with calls into the real production code:

- `from scoring import grade_item` — the real grader (now with `Unscoreable` and
  blank→Unknown from P1).
- P1 added `DownloadResult.fail_kind` and the `UNSCOREABLE` sentinel in
  `compare_url_content`. **The old `eq_license_code_url_reason` cannot reconstruct
  `Unscoreable`** — the old code collapsed "HTML landing page" and "404" into one
  `gt_url_download_failed`. So GT content-type must be **fetched fresh**: for each
  URL row, live-probe the GT URL and classify HTML via the real
  `download.looks_like_html` (or by re-running `compare_url_content` against the
  on-disk inferred file — either is faithful; prefer the smallest code).
- P2 added `download.nuget_candidates(purl)` — probe it live for the ~70 NuGet
  purls to count how many now yield a downloadable LICENSE (empty→file recall).
- P3 added `copyright._is_stray_holder` — apply it to the extracted copyright
  strings to count the OTel-Go-style rows that move Mismatch→Unknown.

The run dir path and extended-CSV constants are already defined at the top of
`rescore.py` (`RUN`, `EXT`, `OUT`). `OUT` is
`ad_hoc_scripts/ad_hoc_scripts_output/` (gitignored — generated tables land there,
not in git). `csv.field_size_limit(10_000_000)` is already set.

DECISIONS H.1 decided: import real functions; re-probe live (do not parse cached
`.txt` dumps); keep the script (deleting it makes the results doc unfalsifiable);
promote findings to a `docs/analysis/` results doc; `src/`+`tests/` stay
production-clean (all experiment code stays in `ad_hoc_scripts/`).

Predicted movements to confirm (from the root-cause analysis): ~64 URL rows →
`Unscoreable`; ~13 copyright rows (OTel-Go) → `Unknown`; NuGet fallback recovers
some empty URL rows → `Hit`/`Unknown`. Exact counts are the deliverable, not
pre-committed targets (raising the headline is a non-goal).

## Files

**Touch (complete list):**

- `ad_hoc_scripts/analysis/rescore.py` — edit: import & call the real P1–P3
  functions; add bounded live probes; emit the movement table.
- `docs/analysis/2026-07-15_run-144424_fact-grade-rescore.md` — create: the
  promoted results doc (counts, method, caveats).
- `docs/BACKLOG.md` — edit: append the accepted residual risks (DECISIONS branch I
  #2–#5) to the "Accepted residual risks" table.

**Do not touch:** any `src/` module (production code is frozen after P1–P3 — this
phase only *reads* it), `tests/`, and anything not listed above. Building a
general "resume-pipeline-from-the-middle" replay engine is explicitly out of
scope (DECISIONS H). Needing an unlisted file means the plan is wrong: record it
here and in your `PLAN.md` block; if you can't proceed, follow **If blocked**.

## Tasks

### T1: Re-score using the real production functions + live probes

- Steps:
  - Import `grade_item` (`scoring`), `looks_like_html` + `nuget_candidates`
    (`download`), `_is_stray_holder` (`copyright`).
  - URL-Mismatch rows: live-probe the GT URL (bounded free HTTP; ~64–70 URLs),
    use the real HTML detector to decide `Unscoreable` vs real Mismatch, and pass
    it through `grade_item` (production grade, not hand-rolled).
  - NuGet rows with empty inferred URL: call `nuget_candidates(purl)` and count how
    many now resolve to a fetchable file (HEAD/GET probe).
  - Copyright-Mismatch rows: apply `_is_stray_holder` and count Mismatch→Unknown.
  - Emit a raw-vs-adjusted movement table (reuse the existing report shape) to
    `OUT/rescore.txt` and stdout.
- Verify: `.\.venv\Scripts\python.exe ad_hoc_scripts\analysis\rescore.py` → exit 0;
  prints a table showing non-zero `Unscoreable`, copyright→Unknown, and NuGet
  recovery counts. (Needs network for the live probes.)
- Commit when green (the script only; `OUT/` is gitignored).

### T2: Promote findings to a results doc

- Steps: write `docs/analysis/2026-07-15_run-144424_fact-grade-rescore.md` — the
  confirmed counts per change, the method (real functions + live probes, run
  frozen), how it compares to the root-cause predictions, and any caveat (e.g.
  live-probe date, HEAD-ref skew for NuGet). Link back to
  `docs/analysis/2026-07-15_run-144424_root-cause-analysis.md` and `docs/DECISIONS.md`.
- Verify: `git status --porcelain` shows the new doc; it cites concrete numbers
  from T1's run.
- Commit when green.

### T3: Migrate accepted residual risks to BACKLOG

- Steps: append DECISIONS branch I residual risks **#2–#5** (NuGet repo-LICENSE
  version skew; HTML-signal false positive; copyright denylist upkeep;
  empty→Unknown flatters recall) as new rows in `docs/BACKLOG.md`'s "Accepted
  residual risks" table, continuing its existing numbering. Keep each to the
  risk + why-accepted, matching the table's columns.
- Verify: `.\.venv\Scripts\python.exe -m pytest -q` → exit 0 (no code touched);
  `docs/BACKLOG.md` contains the four new rows.
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0 (production code untouched — same count as after P3)
2. `.\.venv\Scripts\python.exe ad_hoc_scripts\analysis\rescore.py` → exit 0, movement table printed
3. Fresh review of `git diff <baseline>..HEAD` (baseline = hash in `PLAN.md`)
   against this doc + an over-engineering lens, by a context that didn't implement
   it (subagent given only the diff, this doc, the lens; if unavailable, ask the
   user to review in a new session). Fix findings, re-run 1–2.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe ad_hoc_scripts\analysis\rescore.py` → exit 0, table with non-zero movement counts
- `docs/analysis/2026-07-15_run-144424_fact-grade-rescore.md` exists and cites the counts

## Rollback

To abandon: `git reset --hard <baseline hash from PLAN.md>`, then set Status to
`blocked` in `PLAN.md` with a one-line reason in your Phase-notes block.

## Failure modes

1. Live probes fail (offline / rate-limited) → re-run when connectivity returns;
   this is an ad-hoc analysis, not a test, so a transient network failure is not a
   production defect. Note the probe date in the results doc.
2. `Unscoreable` count is ~0 → you reconstructed it from the old
   `gt_url_download_failed` reason instead of a fresh content-type probe; the old
   reason cannot distinguish HTML from 404 (see capsule).
3. rescore.py drifts from production grading → it must **import** `grade_item`
   etc., never re-implement them; a green re-score against a copy proves nothing.

## Anti-goals

Do not, even if it seems better:

- No pipeline-replay engine, no LLM calls in the re-score (deterministic + free
  HTTP only; the bounded live re-judge of copyright pairs is P3's opt-in).
- No full 380-row live re-run here — it stays opt-in (DECISIONS H).
- No moving analysis code into `src/` or `tests/` — quarantine stays in
  `ad_hoc_scripts/`.
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here" fixes.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (start hash)
   and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block.
   This is the terminal phase — trigger `PLAN.md`'s **On completion** steps
   (graduate durable decisions, stamp COMPLETED, archive the plan directory).
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: {phase goal, one line} | HEAD: {short hash} | Branch: {name}
Files changed: {git diff --name-only <baseline>..HEAD}
Commands + Test status: {gate commands and observed results}
Assumptions / Open questions: {numbered, or "none"}
Next action: {next eligible phase per PLAN.md, or "plan complete"}
```
