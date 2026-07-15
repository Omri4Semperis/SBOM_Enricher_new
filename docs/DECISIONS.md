# SBOM Enricher — Current Decisions

Signed off: 2026-07-15

This is the live decision log. The completed v2 grilling log is preserved at
[`archive/DECISIONS_2026-07-15.md`](./archive/DECISIONS_2026-07-15.md).
Domain vocabulary is defined in [`CONTEXT.md`](./CONTEXT.md); deferred work
lives in [`BACKLOG.md`](./BACKLOG.md).

## Output contract

- `summary.json` groups these fields, in this order, under `run_info`:
  `run_dir`, `run_id`, `run_name`, `model`, `workers`, `components`,
  `cache_hits`, `started_at_utc`, `ended_at_utc`.
- Those fields are not duplicated at the top level. `costs` and `timings`
  remain top-level objects.
- This is a direct schema change for new runs. Existing run artifacts are not
  rewritten, and there is no compatibility layer, migration, or schema-version
  mechanism.

## Cost and call metadata

- Capture raw response, token usage, and cost metadata for every billable
  Claude and GPT-4.1 attempt when the provider exposes them. This includes
  responses later rejected by parsing or contract validation.
- Each component records known per-call and per-phase costs. Missing provider
  metadata is represented as `unknown`, never `$0`.
- A bucket's `total_usd` and the run total are numeric only when every
  contributing billable call has known cost; otherwise the total is `unknown`.
- **Inference Cost** is the subset of Run Cost from calls that produce
  enrichment: Claude license inference, GPT-4.1 LICENSE-file copyright
  extraction, and last-resort Claude web copyright inference. Equality judges
  and connectivity preflight are excluded.
- Run total includes component enrichment and equality-judge calls. It excludes
  connectivity preflight.
- A cache hit incurs `$0` Run Cost. The original component's measured cost is
  stored in new cache entries as Cached Historical Cost for provenance only;
  it is never included in the current run's totals.
- Remove `saved_by_cache_usd`; it describes a counterfactual rather than actual
  spend.
- GPT-4.1 Global Standard prices, verified from the user-supplied official
  pricing table on 2026-07-15, are: input `$2.00`, cached input `$0.50`, and
  output `$8.00` per one million tokens.
- Claude cost uses the CLI's authoritative `total_cost_usd`.

## Copyright fallback chain

When copyright remains `UNKNOWN`, apply this precedence without overwriting an
earlier success:

1. Extract a verbatim statement from the downloaded LICENSE file with GPT-4.1.
2. For npm purls, query registry metadata and accept only `author.name` or the
   string form of `author`; strip email/URL decoration and emit
   `Copyright (c) {name}`. Do not use contributors or maintainers.
3. Ask the configured Claude model to research the web for a source-backed,
   verbatim copyright statement.
4. If all sources fail, keep `UNKNOWN`.

The Claude web fallback returns:

```json
{
  "copyright": "<verbatim copyright statement or UNKNOWN>",
  "reasoning": "<concise sources checked>"
}
```

It uses the existing Claude retry policy, preserves raw/cost/token metadata,
rejects placeholders and unsupported guesses, and counts toward Inference
Cost.

## Documentation and backlog

- BACKLOG #2 (broader deterministic download fallback) remains deferred to
  Omri until ecosystem mix demands it.
- BACKLOG #4 and #6 are removed when their copyright and cost work is delivered;
  remaining rows keep their existing numbers.
- The first Should-fix in [`archive/FULL-REVIEW_2026-07-15.md`](./archive/FULL-REVIEW_2026-07-15.md) is resolved by documenting functional
  cost output and `unknown` semantics, not by adding an obsolete placeholder
  warning. **Resolved 2026-07-15** — the semantics are documented at the
  `summary.py` writer (`build_summary`/`_cost_bucket` docstring).
- The second Should-fix is resolved by adding a fact-checked note to the
  archived v2 plan explaining why phase baselines and Outcome HEADs are not a
  contiguous hash chain. **Resolved 2026-07-15** — note added to
  `docs/plans/archive/v2-enricher/PLAN.md`.

## Validation

- Every phase adds focused automated tests and keeps the full suite green.
- Cost integration is validated once against a live minimal Claude call and a
  live minimal GPT-4.1 call after unit tests pass.
- The live check must demonstrate that ordinary valid provider responses
  produce known component costs and zero unknown-cost calls.
