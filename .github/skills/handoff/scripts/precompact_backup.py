#!/usr/bin/env python3
"""preCompact hook: back up the transcript to .github/backups/.

Backstop only — hooks cannot force HANDOFF.md authorship or rewrite how
compaction summarizes; the handoff skill's model-side triggers (description
+ "When to write one" in its SKILL.md) are the real layer.

Cursor's preCompact is observational: it accepts optional user_message but
cannot inject preserve-instructions into the compaction prompt the way
Claude Code's additionalContext could. This script still backs up the
transcript and optionally nudges the user via user_message.
Never blocks: exits 0 even when the backup fails (warning on stderr).
"""
import json
import os
import shutil
import sys
from datetime import datetime

PRESERVE_NUDGE = (
    "Compaction starting — if you have no fresh docs/HANDOFF.md, consider "
    "writing one first. Preserve: session objective; git branch/HEAD; files "
    "changed and why; failing tests/commands; unverified assumptions; the "
    "single next action."
)


def main() -> int:
    payload: dict[str, object]
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}

    transcript = str(payload.get("transcript_path") or "")
    roots = payload.get("workspace_roots") or []
    cwd = str(
        payload.get("cwd")
        or (roots[0] if isinstance(roots, list) and roots else os.getcwd())
    )
    trigger = str(payload.get("trigger") or "unknown")
    session = str(
        payload.get("conversation_id")
        or payload.get("session_id")
        or "nosession"
    )[:8]

    if transcript and os.path.isfile(transcript):
        backup_dir = os.path.join(cwd, ".github", "backups")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(
            backup_dir, f"transcript-{session}-{stamp}-{trigger}.jsonl"
        )
        try:
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(transcript, dest)
        except OSError as e:
            print(f"precompact_backup: backup failed: {e}", file=sys.stderr)
    else:
        print(
            f"precompact_backup: no transcript at {transcript!r}",
            file=sys.stderr,
        )

    # Cursor preCompact: user_message only (no context injection into compaction).
    print(json.dumps({"user_message": PRESERVE_NUDGE}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
