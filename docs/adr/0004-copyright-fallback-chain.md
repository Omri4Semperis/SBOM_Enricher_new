---
status: accepted
---

# Copyright fallback chain restored: npm author, then Claude web inference

Supersedes ADR-0003. File-only copyright extraction left too many components
`UNKNOWN` in score-bearing runs. Copyright resolution now chains, without
overwriting an earlier success: LICENSE-file extraction (GPT-4.1) → npm
registry `author` (npm purls only, plain HTTP, no LLM cost) → Claude web
inference (billable, source-backed) → `UNKNOWN`. The multi-source blur that
ADR-0003 flagged is accepted as the cost of materially better recall.
