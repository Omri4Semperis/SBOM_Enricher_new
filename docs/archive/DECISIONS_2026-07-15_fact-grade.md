# DECISIONS — grilling of `docs/SUGGESTIONS.md` (archived)

Signed off: 2026-07-15 · Archived: 2026-07-15

Historical grilling log for the fact-grade-first tranche. Requirements are
embodied in `docs/plans/archive/fact-grade-tranche/`, ADR-0006, and
`docs/CONTEXT.md`. Deferred levers + residual risks: `docs/BACKLOG.md`.
Source plan: `docs/archive/SUGGESTIONS_2026-07-15_run-144424.md`. Root cause:
`docs/archive/2026-07-15_run-144424_root-cause-analysis.md`. The companion
deferred list was archived as
`docs/archive/DEFERRED_2026-07-15_fact-grade.md` (items migrated to BACKLOG).

## Branch checklist

- [x] A. Goals / non-goals
- [x] B. Scope / re-cut
- [x] C. Suggestion 1 — GT-not-a-file URL guard
- [x] D. Suggestion 2 — split: prompt-tightening in, LLM third-verdict deferred
- [x] E. Suggestion 3a — NuGet nuspec fallback
- [x] F. Suggestion 3b — OpenTelemetry-Go copyright fix (narrow reject-only guard)
- [x] G. Contracts / schema (EqResult verdict, grade values, score.csv)
- [x] H. Validation — policy set; offline re-score *harness design* → mini-grilling
- [x] I. Open risks (handoff open questions + residual risks)

---

## A. Goals / non-goals

**Decision:** The goal is a **truthful measurement** — stop penalizing the agent
for ground-truth / methodology artifacts, while still surfacing genuine agent
gaps. **Raising the headline all-three-Hit number is an explicit non-goal.**

Rationale: changes 1 and 2 change the *measurement*, not the agent; only change 3
improves the agent. Treating "reach X%" as a goal would incentivize relabeling
real disagreements as "GT-suspect" and hollow out the score.

## B. Scope / re-cut

**Decision:** Re-cut the work into a **fact-grade-first tranche** (defensible by
evidence, cheap first). Committed set for this line of work:

1. Suggestion 1 — GT-not-a-file URL guard (grading-only, verified)
2. Root-cause #3 — empty / no-obtainable license → **Unknown**, not Mismatch
   (grading-only; prerequisite for reasoning about NuGet rows)
3. Suggestion 3a — NuGet nuspec fallback (the one true agent-recall win, verified)
4. Suggestion 3b — OpenTelemetry-Go copyright fix (small, genuine, verified)
5. Judge prompt-tightening (years when holder matches; "and Contributors"
   subset/superset — root-cause #4) rides along; cheap.

**Suggestion 2 (third equality verdict)** is pulled OUT of the committed set and
grilled on its own (branch D) because it is the only "design bet" and it changes
the *meaning* of the output rather than fixing a clear defect.

## C. Suggestion 1 — GT-not-a-file URL guard

### C1. Resulting grade — DECIDED

**Decision:** Introduce a new, distinct **fourth grade `Unscoreable`** (reason
`gt_not_a_file`) for URL rows where the GT URL is provably not a fetchable
license file while the agent already has a good file. **Not `Hit`** (would
inflate the headline, a non-goal), **not `Unknown`** (that means the *agent*
didn't answer; here the agent answered well and the *GT* is defective).

Consequences to carry:
- Widens the locked `CONTEXT.md` **Scoring Outcome** term (was closed at 3:
  hit/mismatch/unknown). Needs a `CONTEXT.md` update + ADR.
- Adds a fourth possible value to the `license_code_url` column in `score.csv`
  and to the all-three-Hit denominator logic (branch G).
- Optional later upgrade: `Unscoreable → Hit` only if the agent's downloaded
  file matches a canonical SPDX text for the declared license (needs an SPDX
  text corpus — deferred, see BACKLOG #8).

### C2. Detection method — DECIDED

**Decision:** Detect by **content-type / HTML signal at fetch time**, not a host
allowlist.

- Fire `Unscoreable` only when the GT fetch returned an **HTML** document
  (landing page, not a raw file) **and** the agent's own file downloaded OK
  (`inf.ok`).
- If the GT URL fails for any *other* reason (404 / network / empty body), keep
  it as **Mismatch** with a distinct reason — that is a real disagreement, not a
  GT-not-a-file artifact.
- Host allowlist rejected: it rots (incomplete; a host can serve both landing
  pages and raw files) and is unnecessary — the HTML signal already covered all
  64 verified rows (pkg.go.dev, Alpine, NuGet, Ubuntu all returned `text/html`).

Cost / contract change: `download.py` currently swallows *why* a fetch failed
(`_try_one` returns `None` for both HTML-reject and HTTP-error). Must surface the
failure **kind** (`html` vs `http_error` vs `network`) so `equality.py` can
branch. Carry to branch G.

## D. Suggestion 2 — split (third verdict vs prompt-tightening)

**Decision:** Split Suggestion 2. **In scope:** judge **prompt-tightening** only,
with the two rules kept narrow and directional (refined during branch I):

(a) **Year tolerance, not year-blindness.** When the holder matches, a *small*
year difference (≈1–2 years off) is equal; do NOT blanket-ignore years. Large
gaps / clearly different ranges are not auto-equal — the judge still decides.

(b) **"and Contributors" / "and others" judged case-by-case, and directional.**
Extra holders are equal only when they are the *same class* just enumerated more
fully, **and** the *inferred* side is the more elaborate/superset one
(inferred ⊇ GT is fine; GT ⊇ inferred is NOT auto-equal). A *different class* of
contributor added is NOT equal.

~21 copyright rows; touches `prompts.equality_copyright_prompts` (and the shared
judge system prompt).

**Deferred (see BACKLOG #6):** the LLM-decided **third verdict**
(`FALSE-GT-suspect`). Rejected from this line of work because it (1) breaks the
`CONTEXT.md` **Equality** TRUE/FALSE contract, (2) needs a human-review workflow
for the GT-suspect pile that does not exist, and (3) asks the same system being
measured to certify its own answers as "independently grounded" — the branch-A
incentive trap. The defensible form of "GT-suspect" is a deterministic,
evidence-based flag, which deserves its own grilling.

## E. Suggestion 3a — NuGet nuspec fallback

**Decision:** Mirror the npm fallback's shape — the fallback's job is a
**downloadable LICENSE file for the URL field**; the nuspec's SPDX id only
informs the name field and must **never fabricate a URL**. A
`nuget_candidates(purl)` (analogous to `npm_candidates`) does:

1. Fetch `api.nuget.org/v3-flatcontainer/{id-lower}/{version}/{id-lower}.nuspec`.
2. If `<repository url=...>` present → derive raw LICENSE candidates from that
   repo (reuse `NPM_LICENSE_FILENAMES` against the repo's raw host) → download
   the real file (consistent with ADR 0002, URL equality by content).
3. If only `<license type="expression">SPDX</license>` and no repo → feeds the
   **name** side only; no file → URL stays empty → grade **Unknown** (branch B /
   root-cause #3), not Mismatch.
4. If only a legacy `licenseUrl` (go.microsoft.com EULA landing page) → no
   fetchable file → **Unknown**.

Boundary: never invent a URL from an SPDX id.

## F. Suggestion 3b — OpenTelemetry-Go copyright fix

**Decision:** **Narrow, reject-only guardrail** that turns a stray/unrelated
copyright holder into `UNKNOWN` (moves the 13 OTel-Go rows Mismatch → Unknown —
honest, not hidden). Positive NOTICE/source-header extraction is **deferred**
(bigger recall play, new source in the ADR-0004 chain).

**Guardrail shape (must be asymmetric):** only *reject* on positive evidence of a
known stray/generic upstream notice (small denylist, e.g. "The Go Authors", "The
Android Open Source Project") that clearly isn't this package. **Never require
the holder to match the package/repo owner** — copyright holders routinely differ
from package names (`lodash` → "John-David Dalton"; `genproto` → "Google LLC"), so
a match-requirement would wrongly nuke hundreds of correct copyrights.

On reject: fall through the resolve_copyright chain to the next source, ending at
`UNKNOWN` rather than emitting the wrong holder.

## G. Contracts / schema

### G1. Representing `Unscoreable` — DECIDED (ponytail choice)

**Decision:** Add a single sentinel verdict **`UNSCOREABLE`** to `EqResult.verdict`,
set by `compare_url_content` *before* the judge (when GT is HTML and `inf.ok`).
It is written to `is_eq_license_code_url` like any verdict; `grade_item` gains one
line: `is_eq == "UNSCOREABLE" → "Unscoreable"`. The **LLM judge stays strictly
TRUE/FALSE** — the sentinel is set by deterministic comparison logic, not the judge.

Chosen over threading the failure `reason` into `grade_item`/`grade_row` because
that changes signatures across all three fields and creates an inconsistent
surface (`is_eq=FALSE` but grade=`Unscoreable`). Sentinel = fewer touchpoints, no
signature change, verdict stays consistent with grade.

Consequence: `CONTEXT.md` **Equality** widens to note the `UNSCOREABLE` sentinel
(judge itself unchanged); covered by the ADR.

### G2. score.csv / all-three-Hit accounting — DECIDED

**Decision:** No `score.csv` schema change. `Unscoreable` appears as another value
in the `license_code_url` column → extra tuple rows in the value-agnostic tally;
no in-product percentage exists to recompute (`summary.py` computes no Hit-rate;
the 46.6% headline lives only in ad-hoc analysis scripts). Convention for any
downstream/analysis Hit-rate: **`Unscoreable` is excluded from the denominator**
(neither Hit nor Mismatch) and reported as its own visible count.

### G3. Mechanism for "empty inference → Unknown" — DECIDED

**Decision:** Generalize `grade_item` so a **blank** inferred value grades as
`Unknown`, same as the literal `"UNKNOWN"`:

```python
if not (inferred or "").strip() or inferred.strip() == "UNKNOWN":
    return "Unknown"
```

Semantics: empty inference = agent didn't answer = "didn't know, didn't guess
wrong" = Unknown. A **non-empty** URL that 404'd stays **Mismatch** (agent guessed
wrong — root-cause 1c). Only *empty* → Unknown.

**Sequencing:** the NuGet fallback (E) must run before this matters, so fetchable
OSS licenses are *found* rather than falling to empty→Unknown; residual empties
then honestly mean "no obtainable license" (EULA case).

## H. Validation

**Decision (policy):** Sign-off gate = **green tests + an offline re-score table
showing the predicted row movements + bounded live spot-checks.** A full 380-row
re-run ($131 / 62 min) is **opt-in, later, NOT required to accept** the work.

Per change:
- Deterministic pieces → **unit tests** (`grade_item` blank→Unknown, `UNSCOREABLE`
  mapping, HTML-signal detection, `nuget_candidates` parsing, copyright denylist).
- Grading/measurement changes (C, G3, F) → **offline re-score** by extending
  `rescore.py` over the existing run's extended CSV + downloaded files; confirm
  movements match root-cause predictions (~64 → Unscoreable, 13 copyright →
  Unknown, etc.). No LLM calls.
- NuGet fallback (E) → **targeted live HTTP probes** of the ~70 NuGet purls (no
  LLM cost).
- Judge prompt-tightening (D) → **targeted re-judge** of only the ~21 flagged
  copyright pairs (bounded GPT cost).

**Explicitly NOT building** a general "resume-pipeline-from-the-middle" replay
engine. Ponytail: extend `rescore.py` with small independent per-change checks.

**Deferred to a short mini-grilling** (own session or opening the implementation
session) — the offline re-score *harness design*:
1. Reuse cached `verify_urls.py` probes vs re-probe GT content-type live?
2. How faithfully must the offline re-score mirror the real
   `grade_item`/`compare_url_content` to be trustworthy (shared code vs
   reimplementation)?
3. Harness lifecycle: throwaway ad-hoc script vs kept fixture/test.

## H.1 Offline re-score harness design (mini-grilling)

### H.1a. Faithfulness — DECIDED

**Decision:** The harness **imports and calls the real production functions** for
everything deterministic (`grade_item`/`grade_row`, the new HTML detector,
`nuget_candidates`, the copyright denylist guard) — never reimplements grade
logic (a green re-score against a copy proves nothing). For facts that need the
network (C's GT content-type; E's fallback), use **bounded live probes**. Note: C
**cannot** be reconstructed from the old `eq_*_reason` — the old code collapsed
"HTML landing page" and "404" into one `gt_url_download_failed`, so the GT
content-type must be fetched fresh.

### H.1b. Reuse cached probes vs re-probe live — DECIDED

**Decision:** **Re-probe live**; do not parse the cached `.txt` dumps. Only
~64–70 URLs, free HTTP, authoritative and current — and exercising the HTML
signal live doubles as an integration check. Cached `url_verification.txt` stays
as corroborating evidence, not harness input (parsing a human-readable snapshot
is more code and less trust).

### H.1c. Harness lifecycle — DECIDED

**Decision:** Split by durability, with a strict cleanliness contract.

- **Kept unit tests** → the existing `tests/` suite, slotted alongside their
  modules (`test_scoring.py`, `test_download.py`, `test_copyright.py`,
  `test_equality.py`), with small inline fixtures and **no run-dir dependency**.
- **Offline re-score over the frozen `20260715_144424` run** → **ad-hoc**, as an
  extension of `ad_hoc_scripts/analysis/rescore.py`; generated tables to
  `ad_hoc_scripts/ad_hoc_scripts_output/`.

**Cleanliness contract:**
- `src/` and `tests/` stay production-clean — only shippable code + kept tests;
  no experiment scaffolding.
- `ad_hoc_scripts/` is the quarantine ("clean" = contained, not empty).
- After the experiment: **promote findings to a `docs/analysis/` results doc**,
  **keep** the reproduction script in `ad_hoc_scripts/` (deleting it makes the
  results doc unfalsifiable). Deleting the script is the user's call at execution
  time; default is keep.

## I. Open risks

The three handoff open questions are resolved by branches C (#1 → Unscoreable),
D (#2 → prompt-tightening only), E (#3 → repo LICENSE, never invent URL).

**Bounded — risk #1 (judge over-correction):** keep the prompt-tightening strictly
rule-scoped per branch D (small year tolerance; directional, same-class "and
others"), never a general "be lenient" instruction. This is the one risk that
threatens goal A (truth), so it is mitigated, not accepted.

**Accepted residual risks (documented, no mitigation now — migrate to BACKLOG at
build time):**

| # | Risk | Why accepted |
|---|------|--------------|
| 2 | NuGet repo-LICENSE version skew — nuspec `repository url` may not be version-pinned, so HEAD's LICENSE could be fetched instead of the packaged version's | Strictly better than empty; only fires when Claude returned nothing |
| 3 | HTML-signal false positive — a real raw license mis-served as `text/html` wrongly becomes `Unscoreable` | Low: body-sniff + `inf.ok` required; and Unscoreable is neutral, not a loss |
| 4 | Copyright denylist upkeep — reject list grows manually as new stray notices appear | Small, additive maintenance |
| 5 | Empty→Unknown flatters recall — a fetchable license missed by a transient flake becomes Unknown, not Mismatch | Unknown is honest ("didn't answer"); retries mitigate |

---

## Recap — all branches resolved

1. **A. Goal:** truthful measurement; raising the headline number is a non-goal.
2. **B. Scope:** re-cut to a fact-grade-first tranche (C, root-cause #3, E, F,
   judge prompt-tightening); the LLM third-verdict pulled out.
3. **C. GT-not-a-file:** new `Unscoreable` grade (reason `gt_not_a_file`),
   detected by HTML content-type at fetch time (not a host allowlist), only when
   the agent's own file downloaded OK.
4. **D. Suggestion 2 split:** prompt-tightening in (narrow year tolerance;
   directional same-class "and others"); LLM third-verdict deferred.
5. **E. NuGet fallback:** nuspec → repo LICENSE file; SPDX id informs the name
   only; never invent a URL.
6. **F. OTel copyright:** narrow reject-only denylist guard → wrong holder
   becomes UNKNOWN; never require holder==owner. Positive NOTICE/header
   extraction deferred.
7. **G. Contracts:** `UNSCOREABLE` sentinel verdict (judge stays TRUE/FALSE);
   no `score.csv` schema change (Unscoreable excluded from any Hit-rate
   denominator); `grade_item` treats blank inference as Unknown.
8. **H. Validation:** tests + offline re-score + bounded live probes; full re-run
   opt-in, not required. No pipeline-replay engine.
9. **H.1. Harness:** import real functions (+ live content-type probes); re-probe
   live; kept unit tests in `tests/`, ad-hoc re-score in
   `ad_hoc_scripts/analysis/`; promote findings to `docs/analysis/`, keep the
   script, `src`/`tests` stay production-clean.
10. **I. Risks:** #1 bounded; #2–#5 accepted as documented residuals.

**Deferred (migrated to `docs/BACKLOG.md` levers #6–#8 + Out of scope; historical
copy in `docs/archive/DEFERRED_2026-07-15_fact-grade.md`):** LLM third-verdict;
Unscoreable→Hit via canonical SPDX; positive NOTICE/header copyright extraction;
SPDX-expression set comparator. **Owner:** Omri.

**Durable-decision note:** the new `Unscoreable` grade widens the `CONTEXT.md`
**Scoring Outcome** term (was closed at 3) and the **Equality** term (adds the
`UNSCOREABLE` sentinel). Done in implementation (ADR-0006 + CONTEXT update).

Status: signed off and implemented — plan at
`docs/plans/archive/fact-grade-tranche/`.
