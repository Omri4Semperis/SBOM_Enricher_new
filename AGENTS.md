# Project goal

This project enriches an input CSV, containing component name & purl, with
license, license url and copyright statement — all fetched online.

Important: Look at `docs/` for special and important documents.

For repo orientation, pipeline/data-flow questions, or module ownership, use
the `architecture-overview` skill. For any test, verification, environment
setup, enrichment run, preflight, or runtime-report task, use `run-and-test`.

## Resuming a handoff

At session start, check for `docs/HANDOFF.md` (repo root):

- Missing → nothing pending; proceed with the user's request.
- Exists, no `Consumed:` line → a live handoff. Surface it and offer to
  continue from its "Next action" before other work — ask, don't hijack a
  session opened for something else.
- When you finish acting on it, add `Consumed: {YYYY-MM-DD}` under its
  title; the stamp, not deletion, is what retires it.
- Exists, already `Consumed:` → spent. Offer to delete it, then proceed.

## AI-docs parity (Cursor ↔ Copilot)

The agent docs are mirrored across two orientations: Cursor (`AGENTS.md`,
`.cursor/skills/`, `.cursor/hooks.json`) and Copilot
(`.github/copilot-instructions.md`, `.github/skills/`, `.github/hooks/`). They
must stay identical.

A start-of-conversation hook runs `python scripts/ai_docs_parity.py`
(`beforeSubmitPrompt` on Cursor, `SessionStart` on Copilot). If it reports
unresolved divergence you MUST, before any other work: tell the user what
differs, which side is more up to date, and a consolidation recommendation,
then ask how to consolidate. If the user approves a divergence, record its
`signature` in `.ai-docs-parity-allow.json`. If the hook did not run (python
unavailable, etc.), run the checker yourself before proceeding.

## Your style

Be Extremely concise. Sacrifice grammar for concision.
