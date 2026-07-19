---
status: accepted
---

# Enriched Output CSV overwrites input columns, keeping originals when ours are bad

`library_approvals_enriched.csv` is the deliverable: the input CSV passed
through, with Enrichment Fields written under the plain names
`license_name` / `license_code_url` / `copyright` (not `inferred_*`). When a
column already exists, our value replaces it unless ours is empty, `UNKNOWN`,
or the component errored — then the original cell is kept. Absent columns are
appended (verbatim, including UNKNOWN/empty) after the input columns in that
canonical order. One row per original input row.

**Rejected:** emitting only `inferred_*` alongside untouched input columns —
cleaner separation, but not what library-approvals consumers want. Always
overwrite even with UNKNOWN — would erase usable prior values when we failed.
