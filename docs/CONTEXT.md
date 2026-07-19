# SBOM Enricher

Enriches a list of software components with their license name, a downloadable
LICENSE-file URL (and the downloaded file), and the copyright statement found in
that file; optionally compares the enrichment against supplied ground truth.

## Language

**Component**:
A single software dependency to be enriched, identified by `component_name`
(with a consistent `purl`). Multiple input rows may share one Component (e.g.
across projects); enrichment runs once per Component. Conflicting identity data
for the same name rejects the run — ADR 0011.

**Cached Historical Cost**:
The LLM charges incurred when a cached enrichment was originally produced.
It is provenance only and is never counted as cost incurred by the current run.
_Avoid_: saved by cache, cache savings

**purl**:
The Package URL of a component (e.g. `pkg:npm/%40awesome.me/kit@1.0.277`). The
canonical, ecosystem-qualified identifier; the primary key for locating the
published package and its raw LICENSE file.
_Avoid_: package id, coordinate

**Enrichment**:
The act of deriving the three inferred fields (license name, license-file URL,
copyright) for a component. The product of a run.

**Enrichment Field**:
One of the three inferred outputs of enrichment — license name, license-file
URL (with its downloaded file), or copyright. Collectively "the enrichment
fields" (or just "fields" where the context is clear). In code the locked
order of ground-truth field names is `GT_FIELDS`.
_Avoid_: element, item — for this meaning.

**Event Log**:
The machine-readable, run-wide timeline of enrichment work — start/end spans
for stages and LLM attempts, with correlation IDs so concurrent components
can be reconstructed. One file per run; for tools and post-hoc analysis, not
for humans reading a single component.
_Avoid_: Story, debug.log, trace dump

**Inference Cost**:
The subset of Run Cost incurred by LLM calls used to produce enrichment,
including billable attempts. It excludes equality testing, connectivity
preflight, and other quality assurance.

**Inferred License Name**:
The license associated with a component, e.g. `MIT`, `GPL-3.0`.

**Inferred License Code URL**:
A reachable, downloadable URL to the component's **own** license/copyright file
— one published for this specific component (its repo or package platform) that
names a concrete copyright holder for it. NOT the canonical/boilerplate text of
the license itself (e.g. the full LGPLv3 legalese naming no holder). When the
standard LICENSE/COPYING is generic boilerplate, an AUTHORS/NOTICE/COPYRIGHT
file that carries the holder is preferred.
_Avoid_: license template, boilerplate license text

**Inferred Copyright**:
The copyright statement inferred for a component. A statement extracted from
the downloaded LICENSE file takes precedence over a package-registry author
fallback, which takes precedence over source-backed web inference.

**Enriched Output CSV**:
The deliverable `library_approvals_enriched.csv` — the input CSV passed through
verbatim, with the three enrichment fields written in: replacing a present
column with our value (unless ours is empty/`UNKNOWN`/errored, then the original
is kept) and adding an absent column outright. One row per original input row
(duplicates repeated). Distinct from `results_*.csv` (audit view, one row per
unique Component) and `results_*_extended.csv` (raw/cost detail). See ADR 0012.
_Avoid_: results csv, output csv — for this specific file.

**Ground Truth**:
User-supplied `license_name` / `license_code_url` / `copyright` columns in the
input, present only for comparison — never used to drive enrichment.
_Avoid_: expected value, baseline

**Audit Mode**:
Run behavior active only when one or more Ground Truth columns are present:
emit `is_eq_*` equality columns and `score.csv`.

**Equality**:
The TRUE/FALSE verdict that an inferred value matches its Ground Truth,
recorded in an `is_eq_*` column. The URL field's equality ladder can also
return the deterministic `UNSCOREABLE` sentinel (see ADR 0006) when the
Ground Truth itself can't be fetched as a file; the judge never issues it —
it stays strictly TRUE/FALSE. URL content comparison reuses the enrichment
license file and does not leave Ground Truth copies in `licenses/` (ADR 0013).

**Scoring Outcome**:
The grade for one inferred enrichment field against Ground Truth: **hit**
(matches), **mismatch** (inferred a wrong value), **unknown** (didn't know,
didn't guess wrong — a blank inferred value grades the same as the literal
`UNKNOWN`), or **unscoreable** (Ground Truth isn't a fetchable license file,
so the field can't be graded either way; excluded from any Hit-rate
denominator — ADR 0006).

**Run Cost**:
The provider charges attributable to component processing in the current run:
enrichment plus equality testing, but not connectivity preflight. Reusing a
cached enrichment contributes zero Run Cost.
_Avoid_: saved cost, cache savings

**Runtime Report**:
The human-readable HTML summary of one enrichment run — run-level timing and
cost, optional audit accuracy, and a per-component breakdown that can show
each component’s inferred Enrichment Fields beside Ground Truth and Scoring
Outcome. Distinct from Story (per-component narrative file) and the Event Log
(machine timeline).
_Avoid_: dashboard, results page, HTML dump

**Story**:
A plain-text, human-readable narrative of everything done to enrich one
component — steps tried, LLM responses, fallbacks, retries, errors, timings.
One per component; for a human, not for machines. Distinct from the Event Log
(run-wide, machine-readable).
_Avoid_: Event Log, debug output, trace dump
