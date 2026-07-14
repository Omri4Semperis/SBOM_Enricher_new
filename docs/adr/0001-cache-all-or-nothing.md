---
status: accepted
---

# Cache is all-or-nothing on `component_name`

Cross-run cache hits key only on `component_name` and return the full
enrichment record (license name, LICENSE URL, copyright, downloaded file) or
nothing — no per-field partial reuse. Only fully-successful rows are written
(no `UNKNOWN` in any inferred field, LICENSE file present), so a re-run
retries exactly the failures and skips the successes.

**Rejected:** the old `(lib_name, version, purl)` key and partial field reuse —
more hit rate, but more flags, stale half-records, and harder Stories.
