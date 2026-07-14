# SBOM Enricher v2 — Backlog

> Explicit parking lot from the grilling session. Nothing here is in v2 scope.
> Pull a lever only when a real run forces it. Residual risks are accepted as-is.

## Deferred levers

| # | Lever | Trigger to pull | Owner |
|---|-------|-----------------|-------|
| 1 | **Restore the consistency judge** (GPT-4.1 self-check on Claude's license reasoning) — trade mismatches for unknowns | License-inference scores look weak (many mismatches vs unknowns) | Omri — post first score-bearing runs |
| 2 | **Broaden deterministic download fallback** beyond npm/unpkg (PyPI, Maven, Cargo, …) | Non-npm ecosystems routinely fail download despite Claude finding a name | Omri — when ecosystem mix demands it |
| 3 | **Mid-run circuit-breaker** (abort / pause on systemic failure, e.g. mass 401s) | All-`UNKNOWN` + Ctrl-C proves too painful in practice | Omri — only if it actually bites |
| 4 | **Restore copyright fallbacks** after file-only extraction fails: npm registry `author`, then Claude web copyright inference (same precedence as old code) | Too many copyright `UNKNOWN`s after file-only GPT-4.1 extraction | Omri — post first score-bearing runs |
| 5 | **Promote GPT-4.1 to a `default.json` knob** | A second GPT deployment appears and needs swapping | Omri — trivial when needed |
| 6 | **Capture LLM cost/tokens/raw on `ComponentResult`** (Claude `total_cost_usd`, GPT-4.1 usage, equality judge meta) so `summary.json` / extended CSV can leave the `unknown` cost marker | Ops shell (P8) ships with unknown costs + `saved_by_cache_usd=0` until callers expose usage | Omri — when cost reporting matters for a real run |

## Accepted residual risks (no mitigation in v2)

| # | Risk | Why accepted |
|---|------|--------------|
| 1 | **Cost / time runaway** — no budget or wall-clock cap; high `workers` can burn until done or Ctrl-C | Progress bar + ETA + Ctrl-C are enough until a run proves otherwise |
| 2 | **Stale cache** — all-or-nothing hit on `component_name`; upstream LICENSE/copyright changes are invisible until `cache_read` is cleared/redirected | Cache is a speed win for identical re-runs; operator owns invalidation |
| 3 | **Provider rate limits** — mid-run 429s become per-row `UNKNOWN`s (retries then fail-closed); no run abort | Matches locked "no circuit-breaker" stance; circuit-breaker is lever #3 |
| 4 | **Wrong-but-confident enrichment** — Claude can return a plausible bad URL/name → mismatch (audit) or silent wrong (non-audit), not `UNKNOWN` | Consistency judge is lever #1; v2 prefers simpler pipeline |

## Out of scope (non-goals, not levers)

Already locked as non-goals for this build — listed here so they don't reappear as "maybe":

- Vulnerability data
- Dependency graphs
- A UI
- Reusing/porting `knowledge/old_code/` (inspiration only)
- Non-CSV input (`.xlsx` / `.json` / TSV)
- Multi-file / directory batching per run
