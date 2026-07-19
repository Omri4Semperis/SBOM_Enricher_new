---
status: accepted
---

# Audit URL equality reuses the enrichment license file; `licenses/` holds only inferred

URL Equality (ADR 0002) still compares LICENSE *content*, but the inferred side
reuses the file already saved during Enrichment — it is never re-downloaded.
The Ground Truth URL is still fetched for the comparison; after comparing, that
GT file is removed from the run's `licenses/` tree so `licenses/` contains only
the inferred license file per component (under the project layout when
applicable). `per_component/{slug}/` may retain both copies for debugging.

**Rejected:** re-downloading the inferred URL as `__eq_inf` beside the
enrichment file — duplicate bytes and wasted wall-clock. Leaving GT files in
`licenses/` — looks like deliverable licenses and violates "one file per
component" for consumers of that tree.
