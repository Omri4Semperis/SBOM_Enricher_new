# P3: honest_rescore_and_doc

**Plan:** fact-grade-review-fixes — clear every review finding so the
fact-grade tranche signs off. This phase is one step toward it; read
`PLAN.md`'s Goal and Context in full before starting. That line orients you;
`PLAN.md` is the source of truth, so don't restate its detail here.

**Your workspace.** Write freely here during implementation. Your only other
editable file is `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other phases' blocks); never another phase's `P*` doc.

**Demo:** `py_compile ad_hoc_scripts/analysis/rescore.py` is green, the
copyright section reports only a guard-trigger count (no fabricated
Mismatch→Unknown movement), and the analysis doc no longer claims "20 of the
78 raw-Mismatch rows → Unknown".

**Goal:** Fix S4 — stop the offline re-score from asserting a resulting grade
for stray-holder rows (production continues through npm + web fallbacks, so
their final grade is not `Unknown`-by-fiat), reporting only the guard-trigger
count; and correct the false Unknown-movement claim in the generated analysis
doc. Also update the `_is_stray_holder` call to P2's new signature.

## Entry criteria

Run each; all must hold before any other work. If any fails, follow
**If blocked** — do not improvise around it.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they carry P2's exact `_is_stray_holder` signature
- [ ] P2's Status is `done` in `PLAN.md`'s phase table
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥132 passed
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

**Critical gotcha:** the frozen run dir this script reads
(`runs/20260715_144424_ClaudeOpu-4-8_380/`) is **absent from this checkout**,
and the script does live HTTP. So `rescore.py` CANNOT be executed here, and you
cannot recompute exact numbers. S4 is therefore a *reasoning-based honesty
correction*, not a recomputation — the doc's claim is wrong regardless of the
exact count. Verify with `py_compile` and doc-text checks, not a live run.

`ad_hoc_scripts/analysis/rescore.py` — re-scores the frozen run using the real
`grade_item`, `looks_like_html`, `nuget_candidates`, `_is_stray_holder`. Key
parts for this phase:

- `adjusted_copyright_grade(row)` (line ~85): currently blanks a stray-holder
  copyright and calls `grade_item("" if stray else inferred, is_eq)`, returning
  `(grade, stray)`. **The S4 bug:** blanking → `Unknown` does not reproduce
  production, which continues through npm + web fallbacks and may end Hit,
  Mismatch, or Unknown. Fix: do not simulate a grade for stray rows — just
  detect and count the guard trigger.
- It calls `_is_stray_holder(inferred)` (line ~90) — **update to P2's new
  signature**, passing the row's package context. Get the exact signature from
  P2's Outcome / the Incoming comment in this phase's `PLAN.md` block. The row
  has `row.get("purl", "")`; a component-name column is also available
  (inspect the CSV header names referenced elsewhere in the file, e.g.
  `component_name`, if `lib_name` is wanted).
- `main()` copyright section (line ~147–159): builds `raw_cp`/`adj_cp` counters
  and prints a `movement_table(...)` for copyright plus
  `"({stray_rows} rows rejected by the stray-holder guard)"`. Fix: drop the
  copyright *movement* table (it asserts the Mismatch→Unknown grade change that
  isn't real) and keep only the guard-trigger count. The `license_code_url`
  section and NuGet-recall section stay as they are.

`docs/archive/2026-07-15_run-144424_fact-grade-rescore.md` — the generated
sign-off doc. The false claim is the `copyright` section (lines ~62–76): a
raw/adjusted table (Mismatch 78→58, Unknown 13→33) and the sentence "20 of the
78 raw-Mismatch rows ... → move to `Unknown`". The "Comparison to root-cause
predictions" table (line ~96–100) repeats "Copyright rows → Unknown ... 20".
Both must be corrected to reflect that the guard only *rejects* a holder;
production then continues through npm + web fallbacks, so no
guaranteed-`Unknown` movement can be claimed from this offline pass.

## Files

**Touch (complete list):**

- `ad_hoc_scripts/analysis/rescore.py` — edit: `adjusted_copyright_grade` →
  guard-trigger detection only; `main()` copyright section → count only, no
  movement table; update the `_is_stray_holder` call to P2's signature.
- `docs/archive/2026-07-15_run-144424_fact-grade-rescore.md` — edit: correct
  the copyright section and the predictions-comparison row.

**Do not touch:** `src/copyright.py`, `src/download.py`, `tests/**`, and
anything not listed under Touch. Needing an unlisted file means the plan is
wrong: record it as a note in this doc and a comment in your `PLAN.md` block;
if the phase can't proceed without it, follow **If blocked**.

## Tasks

### T1: Make the re-score report the guard-trigger count only

- Steps: In `rescore.py`, change `adjusted_copyright_grade(row)` to stop
  simulating a grade: detect whether the row's `inferred_copyright` trips the
  (association-aware) guard and return just that boolean/count — do not call
  `grade_item` with a blanked value for the copyright field. Update the
  `_is_stray_holder(...)` call to P2's new signature (pass `purl` and, if the
  signature takes it, `lib_name`/component name from the row). In `main()`,
  replace the copyright `movement_table(...)` call with a plain line reporting
  only the guard-trigger count and an explicit note that production continues
  through npm + web fallbacks so the final grade is not determined here. Remove
  now-unused copyright counters if they become dead.
- Verify: `.\.venv\Scripts\python.exe -m py_compile ad_hoc_scripts/analysis/rescore.py` → exit 0, no output.
- Commit when green (write the message at commit time: a concise line describing what this task changed).

### T2: Correct the false Unknown-movement claim in the analysis doc

- Steps: In `docs/archive/2026-07-15_run-144424_fact-grade-rescore.md`, rewrite
  the `copyright` section (~lines 62–76): remove the raw/adjusted grade table
  and the "20 ... → move to `Unknown`" sentence; replace with an honest
  statement — the stray-holder guard is *reject-only*; N rows carry a holder the
  guard would reject, after which production continues through the npm + web
  fallback chain, so this offline pass does not establish their final grade
  (Hit/Mismatch/Unknown). If a specific count is stated, frame it strictly as
  "rows that trigger the guard", not "rows that become Unknown". Fix the
  matching row in the "Comparison to root-cause predictions" table (~line 99)
  the same way (guard-trigger count, not an Unknown movement). Do not invent new
  numbers — the run can't be re-executed here; if the old exact figure can't be
  re-derived, describe the guard behavior qualitatively and note the run is not
  reproducible from this checkout.
- Verify: `Select-String -Path docs/archive/2026-07-15_run-144424_fact-grade-rescore.md -Pattern "move to .Unknown."` returns nothing (the false phrasing is gone).
- Commit when green (write the message at commit time: a concise line describing what this task changed).

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥132 passed (this phase
   adds no tests; the suite must still pass — `rescore.py` is ad-hoc and not
   covered, so the count is unchanged from P2's exit state).
2. `.\.venv\Scripts\python.exe -m py_compile ad_hoc_scripts/analysis/rescore.py` → exit 0.
3. Fresh review: the diff `git diff {baseline}..HEAD` (substitute the hash
   recorded in `PLAN.md` at phase start) is reviewed against this doc plus an
   over-engineering lens by a context that did not implement it (subagent given
   only the diff, this doc, and the lens; if subagents are unavailable, stop and
   ask the user to review in a new session). Fix findings, re-run 1–2.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m py_compile ad_hoc_scripts/analysis/rescore.py` → exit 0, no output.
- `Select-String -Path docs/archive/2026-07-15_run-144424_fact-grade-rescore.md -Pattern "move to .Unknown."` → no matches.
- `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, ≥132 passed.

## Anti-goals

Do not, even if it seems better:

- Do not attempt to re-run `rescore.py` end to end or fabricate fresh numbers —
  the frozen run dir is absent and the script needs the network.
- Do not replay the full resolver chain (npm + web) to "prove" the real grade —
  the review explicitly says report only the guard-trigger count.
- Do not touch the `license_code_url` or NuGet-recall sections of either file;
  only the copyright claim is in scope.
- Do not edit `src/copyright.py` to change the signature back for convenience —
  match P2's signature.

## Blocked (2026-07-16)

T1 is done and committed (commit `2d84b29`): `rescore.py`'s
`adjusted_copyright_grade` replaced with `copyright_guard_triggered(row)` —
detects the guard trip via `_is_stray_holder(inferred, purl, lib_name)` (P2's
signature; `lib_name` from `input_csv.parse_component_name(row["component_name"])`)
without simulating a grade. `main()`'s copyright section now prints only the
guard-trigger count plus an explicit note that production continues through
npm + web fallbacks. `py_compile` green, full suite still 136 passed.

T2 is drafted in the working tree (uncommitted) against
`docs/archive/2026-07-15_run-144424_fact-grade-rescore.md`: the false
"20 of the 78 raw-Mismatch rows ... → move to `Unknown`" claim and the
matching "Comparison to root-cause predictions" row are rewritten to state
the guard is reject-only and does not by itself resolve a grade, without
inventing a new count (the frozen run dir is absent from this checkout).

**Why blocked:** this phase's Exit criteria (and T2's own Verify) run:

```
Select-String -Path docs/archive/2026-07-15_run-144424_fact-grade-rescore.md -Pattern "move to .Unknown." → no matches
```

This still matches one line — `~55`, in the `license_code_url` section:
"The other 70 raw-Mismatch rows that move to `Unknown` are exactly the
`inferred_url_download_failed` rows with a **blank** inferred URL..." This
sentence is pre-existing, true, unrelated to S4 (it's P1's real blank→Unknown
grading rule, not a simulated/fabricated grade), and outside this phase's
scope. But this doc's own Anti-goals say: "Do not touch the `license_code_url`
... sections of either file; only the copyright claim is in scope" — so the
literal grep can never return zero matches without violating that explicit
anti-goal. This is a planning bug in the Exit criteria's regex (too broad —
it wasn't written expecting a second, legitimate hit elsewhere in the file),
not evidence of a remaining false claim.

Given the choice between (a) treating the criterion as satisfied in spirit,
(b) rewording the protected line anyway, or (c) blocking, the user chose to
block — the phase doc itself needs the Exit criteria / T2 Verify command
amended (e.g. scope the `Select-String` to the `## copyright` section only,
or otherwise account for the legitimate license_code_url match) before this
phase can be re-attempted and completed.

**Working tree state:** T1 committed; T2's doc edits are uncommitted local
changes (not reverted) so the drafted correction is available once the Exit
criteria is fixed — see `git diff` on
`docs/archive/2026-07-15_run-144424_fact-grade-rescore.md`.

**Resolution (2026-07-16):** user reviewed the collision and ruled it wasn't
the instruction's intent for the Exit criterion to reject an unrelated, true,
out-of-scope sentence — directed the executor to treat this single finding
(the leftover `license_code_url` match) as satisfied and continue. Phase
un-blocked; proceeding with T2 commit and the Validation gate.

## Outcome
Objective: Stop the offline re-score from asserting a resulting grade for
stray-holder copyright rows (report only the guard-trigger count) and correct
the false "20 of 78 → Unknown" claim in the generated analysis doc; update the
`_is_stray_holder` call to P2's new signature.
HEAD: 21180b1 | Branch: master
Files changed: ad_hoc_scripts/analysis/rescore.py,
docs/archive/2026-07-15_run-144424_fact-grade-rescore.md,
docs/plans/fact-grade-review-fixes/P3_honest_rescore_and_doc.md,
docs/plans/fact-grade-review-fixes/PLAN.md
Commands run:
- `py_compile ad_hoc_scripts/analysis/rescore.py` → exit 0, no output.
- `Select-String -Path docs/archive/2026-07-15_run-144424_fact-grade-rescore.md -Pattern "move to .Unknown."` → one match, line 55, in the out-of-scope `license_code_url` section (pre-existing, unrelated, true statement) — accepted per the user's ruling (see Blocked/Resolution above); the copyright section's false claim is gone.
- `pytest -q` → exit 0, 136 passed (unchanged from P2's exit state; this phase adds no tests).
- Fresh review (subagent, generalPurpose, given the diff `cb10194..HEAD` on the two Touch files, this doc, and the ponytail-review tag lens): verdict PASS — no doc-compliance or over-engineering findings, no lens objections.
Test status: `pytest -q` → 136 passed, exit 0.
Assumptions: none.
Open questions:
1. The Exit criteria's `Select-String` pattern is broader than intended (matches an unrelated true sentence outside this phase's scope) — a planning-doc imprecision, not a code issue. No action taken to narrow it since the phase is now terminal/archived; noted here for the historical record only.
Next action: plan complete — every phase (P1, P2, P3) shows `done`; proceeding to `PLAN.md`'s On completion (stamp + archive).

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, then report to the
user and stop. Do not guess, do not widen the file list, do not edit another
phase's doc. To abandon work already done, roll back with
`git reset --hard {baseline hash from PLAN.md's phase table}`.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (the start
   hash) and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block.
   This is the terminal phase — once done, follow `PLAN.md`'s **On completion**
   (stamp COMPLETED, archive the plan directory).
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: {phase goal, one line}
HEAD: {git rev-parse --short HEAD} | Branch: {git branch --show-current}
Files changed: {git diff --name-only <baseline>..HEAD output}
Commands run: {the Verify/gate commands and their observed results}
Test status: {suite command + observed result}
Assumptions: {numbered, or "none"}
Open questions: {numbered, or "none"}
Next action: {the next eligible phase per PLAN.md's table, or "plan complete"}
```
