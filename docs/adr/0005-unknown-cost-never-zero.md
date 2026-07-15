---
status: accepted
---

# Missing cost metadata renders as unknown, never $0

A cost cell or total is a real number only when every contributing billable
LLM call reports known cost; if any call's cost is unavailable, the total is
`unknown` rather than defaulting to `$0`, which would understate spend and
read as free work. `saved_by_cache_usd` was removed for the same reason — it
described a counterfactual, not actual spend. A cache hit still contributes
exactly `$0` Run Cost (real, not missing); the original run's measured cost
is retained per cache entry as Cached Historical Cost, for provenance only,
and is never counted in any current run's total.
