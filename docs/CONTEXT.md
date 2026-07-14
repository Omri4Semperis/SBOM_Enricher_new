# SBOM Enricher

Enriches a list of software components with their license name, a downloadable
LICENSE-file URL (and the downloaded file), and the copyright statement found in
that file; optionally compares the enrichment against supplied ground truth.

## Language

**Component**:
A single software dependency to be enriched — one input row, identified by a
`component_name` and a `purl`.

**purl**:
The Package URL of a component (e.g. `pkg:npm/%40awesome.me/kit@1.0.277`). The
canonical, ecosystem-qualified identifier; the primary key for locating the
published package and its raw LICENSE file.
_Avoid_: package id, coordinate

**Enrichment**:
The act of deriving the three inferred fields (license name, license-file URL,
copyright) for a component. The product of a run.

**Inferred License Name**:
The license associated with a component, e.g. `MIT`, `GPL-3.0`.

**Inferred License Code URL**:
A reachable, downloadable URL to the component's actual LICENSE file, ideally
from the raw publication of the component.

**Inferred Copyright**:
The copyright statement found **in the downloaded LICENSE file**. If no file was
downloaded, copyright cannot be inferred.

**Ground Truth**:
User-supplied `license_name` / `license_code_url` / `copyright` columns in the
input, present only for comparison — never used to drive enrichment.
_Avoid_: expected value, baseline

**Audit Mode**:
Run behavior active only when one or more Ground Truth columns are present:
emit `is_eq_*` equality columns and `score.csv`.

**Equality**:
The TRUE/FALSE verdict that an inferred value matches its Ground Truth,
recorded in an `is_eq_*` column.

**Scoring Outcome**:
The grade for one inferred item against Ground Truth: **hit** (matches),
**mismatch** (inferred a wrong value), or **unknown** (didn't know, didn't
guess wrong).

**Story**:
A plain-text, human-readable narrative of everything done to enrich one
component — steps tried, LLM responses, fallbacks, retries, errors, timings.
One per component; for a human, not for machines.
_Avoid_: log, trace, debug output
