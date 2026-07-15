---
status: superseded by ADR-0004
---

# Copyright is extracted only from the downloaded LICENSE file

Inferred copyright comes solely from GPT-4.1 reading a successfully downloaded
LICENSE file (verbatim statement or `UNKNOWN`). No npm-author registry fallback
and no Claude web copyright inference in v2 — if there is no file, or the file
has no real holder, the field stays `UNKNOWN`.

**Rejected for v2 (parked as backlog #4):** the old npm-author → Claude-web
ladder. It raised recall but mixed sources, complicated Stories/scoring, and
blurred the rule that copyright is “what the LICENSE file says.”
