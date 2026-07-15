# P1: grading_honesty

**Plan:** fact-grade-first tranche — truthful audit measurement without gaming
the headline. Read `PLAN.md`'s Goal and Context in full before starting.

**Your workspace.** This doc is writable (decisions, dead ends, findings). You
may also edit `PLAN.md` (your table row, your Phase-notes block, Incoming
comments in other blocks). Never edit another phase's `P*` doc.

**Demo:** `grade_item` returns `"Unscoreable"` for an `UNSCOREABLE` URL verdict
and `"Unknown"` for a blank inferred value, and `compare_url_content` returns
`UNSCOREABLE` when the GT URL is an HTML landing page and the inferred file
downloaded OK — shown by the P1 tests in `test_scoring/equality/download.py`.

**Goal:** Add the **`Unscoreable`** URL grade end to end: `download.py` surfaces
*why* a fetch failed (`fail_kind`), `compare_url_content` turns "GT is an HTML
landing page + our own file is fine" into a deterministic `UNSCOREABLE` sentinel,
and `grade_item` maps that to `"Unscoreable"`. Also grade a **blank** inferred
value as `Unknown` (not `Mismatch`). Record the two vocabulary changes in
`CONTEXT.md` + a new ADR.

## Entry criteria

Run each; all must hold before other work. If any fails, follow **If blocked**.

- [ ] Read this phase's block in `PLAN.md`, including any **Incoming comments** — they amend this doc
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, `119 passed`
- [ ] `git status --porcelain` → empty (clean tree)

## Context capsule

`src/download.py`:
- `DownloadResult` (`@dataclass`): `resolved_url`, `saved_path`, `error`,
  `original_url`, `attempts: list[str]`, `.ok` (`saved_path is not None`).
- `_try_one(url, dest_dir, slug, attempts) -> Path | None` fetches one candidate
  (rewrite viewer→raw, reject templates, `_get_bytes` via `with_retries`, reject
  HTML via `looks_like_html(body, content_type)`, else write). It returns `None`
  for **every** failure kind — that is the information loss this phase fixes.
- `_get_bytes` raises `_HttpFail(kind, message)` with message like `http_404`,
  `network:<Class>`, `timeout:<...>`, `empty_body`; `_try_one` catches it as
  `except Exception as exc`.
- `fetch_license_file(claude_url, purl, dest_dir, slug)` tries the claude URL then
  npm candidates; on total failure sets `error = "download_failed"`.

`src/equality.py`:
- `EqResult(verdict, reason, meta=CallMeta())`, frozen.
- `compare_url_content(inferred_url, gt_url, dest_dir, slug, *, client=None)`:
  fetch `inf` → `FALSE "inferred_url_download_failed"` if `not inf.ok`; fetch `gt`
  → `FALSE "gt_url_download_failed"` if `not gt.ok`; else bytes→normalized→judge.
  **Both fetches pass empty purl** (no fallback), so each result reflects one URL.
  When GT is checked, `inf.ok` is already True.

`src/scoring.py` — `grade_item(inferred, is_eq)`: `strip()=="UNKNOWN"`→`"Unknown"`;
`is_eq=="TRUE"`→`"Hit"`; else `"Mismatch"`. `grade_row` passes `is_eq` straight
through, so the `UNSCOREABLE` string flows in unchanged.

Test conventions: equality tests monkeypatch `equality.fetch_license_file` to
return a `DownloadResult` (`test_gt_url_download_fail` uses one with no `fail_kind`
→ must stay `FALSE`); download tests monkeypatch `download.requests.get`
(`_ok_response`, `_status_response` helpers).

## Files

**Touch (complete list):**

- `src/download.py` — edit: add `fail_kind: str = ""` to `DownloadResult`; make
  `_try_one` report the kind; record it on the result.
- `src/equality.py` — edit: `compare_url_content` returns `UNSCOREABLE` when
  `gt.fail_kind == "html"` (inf already ok).
- `src/scoring.py` — edit: `grade_item` maps `UNSCOREABLE`→`"Unscoreable"` and
  blank inferred → `"Unknown"`.
- `tests/test_download.py` — edit: assert `fail_kind` classification.
- `tests/test_equality.py` — edit: assert `UNSCOREABLE` verdict + reason.
- `tests/test_scoring.py` — edit: assert both new `grade_item` branches.
- `docs/CONTEXT.md` — edit: widen **Scoring Outcome** and **Equality** terms.
- `docs/adr/0006-unscoreable-grade.md` — create: the durable decision record.

**Do not touch:** `src/pipeline.py` (the sentinel flows through `grade_row`
unchanged), `results_csv.py`, `summary.py`, anything not listed above. Needing an
unlisted file means the plan is wrong — record it and follow **If blocked**.

## Tasks

### T1: Surface the fetch failure kind in `download.py`

- Steps: add `fail_kind: str = ""` to `DownloadResult`. Change `_try_one` to
  return `tuple[Path | None, str]`: success `(path, "")`; template reject
  `(None, "template")`; HTML reject `(None, "html")`; caught fetch exception →
  classify the message (`network`/`timeout` prefix → `(None, "network")`, else
  `(None, "http_error")`). In `fetch_license_file`, unpack at both call sites;
  track the **last** non-empty kind and set `result.fail_kind` before the failure
  `return`.
- Verify: add `test_fetch_html_sets_fail_kind` (`text/html` → `not ok`,
  `fail_kind=="html"`) and `test_fetch_http_error_fail_kind` (404 →
  `fail_kind=="http_error"`). `pytest tests/test_download.py -q` → exit 0.
- Commit when green.

### T2: Emit the `UNSCOREABLE` sentinel in `compare_url_content`

- Steps: after the GT fetch, when `gt.fail_kind == "html"` return
  `EqResult("UNSCOREABLE", "gt_not_a_file")`, else the existing
  `EqResult("FALSE", "gt_url_download_failed")`. (`inf.ok` is already True here.)
- Verify: add `test_gt_html_landing_page_unscoreable` — ok inferred file + GT
  `DownloadResult(error="download_failed", fail_kind="html")`; assert
  `verdict=="UNSCOREABLE"`, `reason=="gt_not_a_file"`, `meta.billable_calls==0`.
  Confirm `test_gt_url_download_fail` (no `fail_kind`) still asserts FALSE.
  `pytest tests/test_equality.py -q` → exit 0.
- Commit when green.

### T3: Map the grade in `grade_item` (both new branches)

- Steps: edit `grade_item` — blank OR literal `UNKNOWN` →`"Unknown"`
  (`if not (inferred or "").strip() or inferred.strip() == "UNKNOWN": return "Unknown"`);
  `is_eq == "UNSCOREABLE"` → `"Unscoreable"`; `is_eq == "TRUE"` → `"Hit"`; else
  `"Mismatch"`.
- Verify: extend `test_grade_item_hmu` with `grade_item("", "FALSE")=="Unknown"`,
  `grade_item("   ", "TRUE")=="Unknown"`, `grade_item("https://x","UNSCOREABLE")=="Unscoreable"`.
  `pytest tests/test_scoring.py -q` → exit 0.
- Commit when green.

### T4: Record the durable vocabulary changes

- Steps: in `docs/CONTEXT.md`, widen **Scoring Outcome** with a fourth value
  **unscoreable** (GT is not a fetchable license file → field can't be graded;
  excluded from any Hit-rate denominator) and note that a blank inference grades
  as unknown; widen **Equality** to note the deterministic `UNSCOREABLE` sentinel
  (judge stays TRUE/FALSE). Create `docs/adr/0006-unscoreable-grade.md` mirroring
  `docs/adr/0002-url-equality-by-content.md`'s format. Decision: HTML content-type
  at fetch time (not a host allowlist), only when the agent's file downloaded OK;
  `UNSCOREABLE` sentinel; excluded from Hit-rate. Rejected: host allowlist (rots);
  `Hit` (inflates headline) or `Unknown` (implies agent failed).
- Verify: `pytest -q` → exit 0; `git status --porcelain` shows both doc paths.
- Commit when green.

## Validation gate

All of these, in order, before Exit criteria:

1. `.\.venv\Scripts\python.exe -m pytest -q` → exit 0, `119 + <new tests> passed`
2. Fresh review of `git diff <baseline>..HEAD` (baseline = hash in `PLAN.md`)
   against this doc + an over-engineering lens, by a context that didn't implement
   it (subagent given only the diff, this doc, the lens; if unavailable, ask the
   user to review in a new session). Fix findings, re-run 1 — but a lens finding on
   something this doc explicitly ordered (e.g. the three-way `fail_kind`) is NOT
   fixed; record it here.

## Exit criteria

Runnable proof the Demo is real:

- `.\.venv\Scripts\python.exe -m pytest tests/test_scoring.py::test_grade_item_hmu -q` → exit 0
- `.\.venv\Scripts\python.exe -m pytest tests/test_equality.py -k unscoreable -q` → exit 0, ≥1 passed

## Rollback

To abandon: `git reset --hard <baseline hash from PLAN.md>`, then set Status to
`blocked` in `PLAN.md` with a one-line reason in your Phase-notes block.

## Failure modes

1. `test_gt_url_download_fail` breaks → you branched on `not gt.ok` without
   requiring `fail_kind == "html"`; a plain failure (`fail_kind == ""`) must stay
   `FALSE "gt_url_download_failed"`.
2. `fail_kind` never becomes `"html"` → `_try_one`'s HTML reject must return
   `(None, "html")` and `fetch_license_file` must copy it onto `result.fail_kind`
   (confirm the single-URL GT path propagates it).

## Anti-goals

Do not, even if it seems better:

- No `Unscoreable → Hit` upgrade via SPDX text (deferred — `docs/DEFERRED.md`).
- No `score.csv` schema change — `Unscoreable` is just another value in the
  existing `license_code_url` column (DECISIONS G2).
- No change to the judge's TRUE/FALSE contract — the sentinel is deterministic.
- Nothing beyond this doc's Tasks: no extra abstractions or "while I'm here" fixes.

## If blocked

Set this phase's Status to `blocked` in `PLAN.md`'s table (fill Baseline and
Updated), add a one-line reason to your Phase-notes block, report to the user and
stop. Do not guess or widen the file list.

## On completion

1. Every Entry/Validation/Exit item passed — re-check, don't recall.
2. In `PLAN.md`: set this phase's Status to `done`, fill Baseline (start hash)
   and Updated (today).
3. In `PLAN.md`, reflect a concise outcome into this phase's Phase-notes block.
4. Record the full outcome in this doc under an **Outcome** heading:

```txt
## Outcome
Objective: {phase goal, one line} | HEAD: {short hash} | Branch: {name}
Files changed: {git diff --name-only <baseline>..HEAD}
Commands + Test status: {gate commands and observed results}
Assumptions / Open questions: {numbered, or "none"}
Next action: {next eligible phase per PLAN.md, or "plan complete"}
```

## Outcome

Objective: add the `Unscoreable` URL grade end to end (fail_kind →
UNSCOREABLE sentinel → grade) and grade a blank inferred value as Unknown |
HEAD: 97ef9d5 | Branch: master

Files changed: `docs/CONTEXT.md`, `docs/adr/0006-unscoreable-grade.md`,
`src/download.py`, `src/equality.py`, `src/scoring.py`,
`tests/test_download.py`, `tests/test_equality.py`, `tests/test_scoring.py`

Commands + Test status:
- Entry: `pytest -q` → exit 0, `119 passed`; `git status --porcelain` → empty. Both held.
- T1: `pytest tests/test_download.py -q` → exit 0, `18 passed`.
- T2: `pytest tests/test_equality.py -q` → exit 0, `10 passed`.
- T3: `pytest tests/test_scoring.py -q` → exit 0, `4 passed`.
- T4: `pytest -q` → exit 0, `122 passed`; `git status --porcelain` showed both doc paths.
- Validation gate: `pytest -q` → exit 0, `122 passed`. Fresh-context subagent
  review (`generalPurpose`, readonly, diff `330b0c4..HEAD` + this doc + the
  `ponytail-review` tag definitions) → full spec conformance (all 8 Files
  touched, none extra; both Do-not-touch files confirmed untouched; T1-T4 all
  pass; both Failure modes avoided; no Anti-goal violations); no
  over-engineering findings beyond two doc-mandated items (the four-way
  `fail_kind` classification and the fourth `Unscoreable` grade value — both
  explicitly ordered by this doc's Tasks, recorded here per the gate's
  instruction, not fixed); no correctness issues found.
- Exit: `pytest tests/test_scoring.py::test_grade_item_hmu -q` → exit 0, `1
  passed`; `pytest tests/test_equality.py -k unscoreable -q` → exit 0, `1
  passed, 9 deselected`.

Assumptions / Open questions: none.

Next action: next eligible phase per `PLAN.md` is P2 (`nuget_nuspec_fallback`)
or P3 (`copyright_honesty`) — both depend on nothing and are `pending`.
