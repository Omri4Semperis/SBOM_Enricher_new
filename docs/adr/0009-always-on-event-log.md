---
status: accepted
---

# Always-on Event Log; Story stays the human narrative

Every run writes `events.jsonl` under the run dir: one JSON object per line,
flushed per record, with correlation IDs (run / component index / slug /
worker-slot / op) and start/end spans down to LLM retry attempts. The writer
is thread-safe (blocking work runs in `to_thread`); uninitialized = no-op so
tests stay silent. Summarize with `src/event_report.py` (streaming, bounded
output) — never dump the raw file into a model context.

**Why always-on:** gating behind a flag would miss the runs you most need to
diagnose (hangs, time-to-first-row, GPT attempt pathology). Append-only JSONL
I/O is cheap relative to LLM walls.

**Rejected:**

- Gated / env-flag Event Log — off by default loses the interesting runs.
- Replacing Story with the Event Log — Story is the per-component human
  narrative; the Event Log is the cross-component machine timeline. Both stay.
- Reconstructing concurrency from `story.txt` mtimes — fragile, no true
  starts, no attempt-level detail (see `ad_hoc_scripts/analysis/`).
