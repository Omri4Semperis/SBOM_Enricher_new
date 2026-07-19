---
status: accepted
---

# Duplicate `component_name` is allowed; only conflicting identity data rejects

Input may repeat the same `component_name` (e.g. one component in several
projects). Enrichment still runs once per unique name. Duplicate rows are a
conflict — and fail the whole run — only when `purl` or any present Ground Truth
field differs after aggressive normalization (trim, collapse whitespace,
case-insensitive). Non-conflicting duplicates keep the first occurrence's
literals in the deduped `results_*.csv` outputs; the Enriched Output CSV keeps
every input row.

**Rejected:** reject-on-any-duplicate (previous behavior) — too strict for
multi-project inputs. Skip-conflicting-rows — leaves a silent partial run.
Enrich-every-row independently — wastes work and can diverge for the same name.
