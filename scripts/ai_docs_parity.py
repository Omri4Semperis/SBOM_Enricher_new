#!/usr/bin/env python3
"""AI-docs parity checker (Cursor <-> Copilot).

Verifies the two agent-doc "orientations" stay identical:

  Cursor side                     Copilot side
  -----------                     ------------
  AGENTS.md                  <->  .github/copilot-instructions.md
  .cursor/skills/<x>/**      <->  .github/skills/<x>/**
  .cursor/hooks.json         <->  .github/hooks/*.json   (semantic/mapped)

Comparison is NORMALIZED: line endings, trailing whitespace and the platform
path tokens `.cursor` / `.github` are canonicalized, so an intentional platform
path difference never flags -- any *other* textual difference does.

"More up to date" is decided by file mtime only.

A divergence can be pre-approved in `.ai-docs-parity-allow.json` (the record of
"a previous user remark allows it"). An allow entry is keyed on the normalized
content hashes of BOTH sides, so if either file changes again the approval
auto-expires and the divergence resurfaces.

Exit codes (text/cursor emit): 0 = in parity (or fully allowed), 2 = unresolved
divergence. `--emit copilot` always exits 0 and delivers the report through the
SessionStart `systemMessage` contract instead (blocking is enforced by the
mandate text + copilot-instructions.md, not by aborting the session).

Stdlib only. Runtime-path assumptions (hook I/O contracts) are documented inline
and may need tuning to a specific Cursor/Copilot build.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = REPO_ROOT / ".ai-docs-parity-allow.json"

# Escape hatch: if the user's prompt contains this phrase, the current unresolved
# divergences are recorded in the allowlist and the turn proceeds -- so a hard
# block can never deadlock the conversation.
ESCAPE_RE = re.compile(r"parity:\s*ignore", re.IGNORECASE)
ESCAPE_PHRASE = "parity: ignore"

# Files whose *content* we do not want to compare even if present in a skill dir
# (caches, compiled artifacts, backups).
IGNORE_NAMES = {".DS_Store"}
IGNORE_SUFFIXES = {".pyc"}
IGNORE_DIR_PARTS = {"__pycache__", "backups"}

# YAML frontmatter keys that are platform-specific and must be ignored when they
# appear on only one side (none needed today; kept for forward-compat).
IGNORE_FRONTMATTER_KEYS: set[str] = set()

DIFF_CONTEXT_LINES = 3
DIFF_MAX_LINES = 40

# Cursor hook event name  <->  Copilot hook event name  ->  canonical name.
EVENT_CANON = {
    # cursor
    "beforeShellExecution": "pre_tool",
    "preCompact": "pre_compact",
    "beforeSubmitPrompt": "session_start",
    # copilot
    "PreToolUse": "pre_tool",
    "PreCompact": "pre_compact",
    "SessionStart": "session_start",
    "UserPromptSubmit": "session_start",
}


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
def canon_paths(text: str) -> str:
    """Collapse the two platform path prefixes to a single placeholder."""
    return re.sub(r"\.cursor|\.github", "<P>", text)


def normalize_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if IGNORE_FRONTMATTER_KEYS:
        text = _strip_frontmatter_keys(text)
    lines = [ln.rstrip() for ln in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    text = "\n".join(lines)
    return canon_paths(text)


def _strip_frontmatter_keys(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    if end == -1:
        return text
    fm = text[4:end]
    body = text[end:]
    kept = [
        ln
        for ln in fm.split("\n")
        if not any(ln.startswith(f"{k}:") for k in IGNORE_FRONTMATTER_KEYS)
    ]
    return "---\n" + "\n".join(kept) + body


def norm_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:16]


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# --------------------------------------------------------------------------- #
# Divergence records
# --------------------------------------------------------------------------- #
class Diff:
    """One parity finding between a cursor-side and copilot-side artifact."""

    def __init__(self, pair_id, kind, cursor_path, github_path,
                 cursor_hash="", github_hash="", detail=""):
        self.pair_id = pair_id          # stable id used by the allowlist
        self.kind = kind                # "content" | "missing" | "hook"
        self.cursor_path = cursor_path  # str or None
        self.github_path = github_path  # str or None
        self.cursor_hash = cursor_hash
        self.github_hash = github_hash
        self.detail = detail

    def signature(self) -> str:
        return f"{self.pair_id}|{self.cursor_hash}|{self.github_hash}"

    def newer_side(self) -> str | None:
        cp = REPO_ROOT / self.cursor_path if self.cursor_path else None
        gp = REPO_ROOT / self.github_path if self.github_path else None
        cm = cp.stat().st_mtime if cp and cp.exists() else None
        gm = gp.stat().st_mtime if gp and gp.exists() else None
        if cm is None and gm is None:
            return None
        if cm is None:
            return "copilot"
        if gm is None:
            return "cursor"
        if abs(cm - gm) < 1e-6:
            return None
        return "cursor" if cm > gm else "copilot"


# --------------------------------------------------------------------------- #
# Skill / instruction file comparison
# --------------------------------------------------------------------------- #
def _iter_files(base: Path):
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.name in IGNORE_NAMES or p.suffix in IGNORE_SUFFIXES:
            continue
        if any(part in IGNORE_DIR_PARTS for part in p.relative_to(base).parts):
            continue
        yield p.relative_to(base)


def compare_tree(cursor_base: Path, github_base: Path, pair_prefix: str):
    diffs: list[Diff] = []
    cursor_files = set(_iter_files(cursor_base)) if cursor_base.exists() else set()
    github_files = set(_iter_files(github_base)) if github_base.exists() else set()

    for rel in sorted(cursor_files | github_files):
        cpath = cursor_base / rel
        gpath = github_base / rel
        rel_posix = rel.as_posix()
        pair_id = f"{pair_prefix}/{rel_posix}"
        cur_rel = str((cursor_base / rel).relative_to(REPO_ROOT))
        gh_rel = str((github_base / rel).relative_to(REPO_ROOT))

        if rel not in github_files:
            diffs.append(Diff(pair_id, "missing", cur_rel, None,
                              detail="present on cursor side, absent on copilot side"))
            continue
        if rel not in cursor_files:
            diffs.append(Diff(pair_id, "missing", None, gh_rel,
                              detail="present on copilot side, absent on cursor side"))
            continue

        ctext = read_text(cpath)
        gtext = read_text(gpath)
        if ctext is None or gtext is None:
            # binary or unreadable -> compare raw bytes
            if cpath.read_bytes() != gpath.read_bytes():
                diffs.append(Diff(pair_id, "content", cur_rel, gh_rel,
                                  detail="binary content differs"))
            continue
        ch, gh = norm_hash(ctext), norm_hash(gtext)
        if ch != gh:
            udiff = _unified(ctext, gtext, cur_rel, gh_rel)
            diffs.append(Diff(pair_id, "content", cur_rel, gh_rel, ch, gh, udiff))
    return diffs


def _unified(ctext: str, gtext: str, cur_rel: str, gh_rel: str) -> str:
    cl = normalize_text(ctext).split("\n")
    gl = normalize_text(gtext).split("\n")
    lines = list(difflib.unified_diff(
        cl, gl, fromfile=cur_rel, tofile=gh_rel,
        n=DIFF_CONTEXT_LINES, lineterm=""))
    if len(lines) > DIFF_MAX_LINES:
        lines = lines[:DIFF_MAX_LINES] + [f"... ({len(lines) - DIFF_MAX_LINES} more diff lines)"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Hook (semantic) comparison
# --------------------------------------------------------------------------- #
def _canon_command(cmd: str) -> str:
    cmd = canon_paths(cmd.replace("\\", "/")).strip().lower()
    cmd = re.sub(r"--emit\s+\w+", "", cmd)          # platform-selecting flag
    cmd = re.sub(r"--block\b", "", cmd)              # enforcement-mode flag
    toks = cmd.split()
    if toks and (toks[0] in {"python", "python3", "py"}
                 or toks[0].endswith("python.exe") or toks[0].endswith("python")):
        toks = toks[1:]                              # drop interpreter token
    return " ".join(toks).strip()


def _load_cursor_hooks(path: Path):
    triples = set()
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for event, entries in (data.get("hooks") or {}).items():
        canon_ev = EVENT_CANON.get(event, event)
        for e in entries:
            triples.add((canon_ev, e.get("matcher", ""), _canon_command(e.get("command", ""))))
    return triples


def _load_copilot_hooks(hooks_dir: Path):
    triples = set()
    if not hooks_dir.exists():
        return triples
    for jf in sorted(hooks_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for event, entries in (data.get("hooks") or {}).items():
            canon_ev = EVENT_CANON.get(event, event)
            for e in entries:
                triples.add((canon_ev, e.get("matcher", ""), _canon_command(e.get("command", ""))))
    return triples


def compare_hooks(cursor_hooks: Path, copilot_hooks_dir: Path):
    cur = _load_cursor_hooks(cursor_hooks)
    gh = _load_copilot_hooks(copilot_hooks_dir)
    diffs: list[Diff] = []
    for triple in sorted(cur - gh):
        diffs.append(Diff(
            f"hooks/{triple[0]}::{triple[2]}", "hook",
            str(cursor_hooks.relative_to(REPO_ROOT)), None,
            cursor_hash=_triple_hash(triple),
            detail=f"cursor has hook [{triple[0]}] `{triple[2]}` (matcher={triple[1]!r}); "
                   f"missing on copilot side"))
    for triple in sorted(gh - cur):
        diffs.append(Diff(
            f"hooks/{triple[0]}::{triple[2]}", "hook",
            None, str(copilot_hooks_dir.relative_to(REPO_ROOT)),
            github_hash=_triple_hash(triple),
            detail=f"copilot has hook [{triple[0]}] `{triple[2]}` (matcher={triple[1]!r}); "
                   f"missing on cursor side"))
    return diffs


def _triple_hash(triple) -> str:
    return hashlib.sha256("|".join(triple).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Allowlist
# --------------------------------------------------------------------------- #
def load_allowed_signatures() -> dict[str, dict]:
    if not ALLOWLIST.exists():
        return {}
    try:
        data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out = {}
    for entry in data.get("allow", []):
        sig = entry.get("signature")
        if sig:
            out[sig] = entry
    return out


def allowlist_add(diffs: list["Diff"]) -> int:
    """Record the signatures of `diffs` as approved. Returns count newly added."""
    data: dict = {}
    if ALLOWLIST.exists():
        try:
            data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    allow = data.get("allow", [])
    existing = {e.get("signature") for e in allow}
    today = date.today().isoformat()
    added = 0
    for d in diffs:
        sig = d.signature()
        if sig not in existing:
            allow.append({"signature": sig,
                          "reason": f"user override: '{ESCAPE_PHRASE}'",
                          "added": today})
            existing.add(sig)
            added += 1
    data["allow"] = allow
    ALLOWLIST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return added


def read_hook_stdin() -> str:
    """Return the hook's stdin payload (the user's prompt for prompt events).

    Returns "" when run interactively (a TTY), so manual runs never block.
    """
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return ""
        return sys.stdin.read() or ""
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def collect_diffs() -> list[Diff]:
    diffs: list[Diff] = []

    # Top-level instructions.
    agents = REPO_ROOT / "AGENTS.md"
    copilot = REPO_ROOT / ".github" / "copilot-instructions.md"
    a, c = read_text(agents), read_text(copilot)
    if a is None or c is None:
        diffs.append(Diff("instructions/AGENTS", "missing",
                          "AGENTS.md" if a is not None else None,
                          ".github/copilot-instructions.md" if c is not None else None,
                          detail="one of the top-level instruction files is missing"))
    elif norm_hash(a) != norm_hash(c):
        diffs.append(Diff("instructions/AGENTS", "content", "AGENTS.md",
                          ".github/copilot-instructions.md",
                          norm_hash(a), norm_hash(c),
                          _unified(a, c, "AGENTS.md", ".github/copilot-instructions.md")))

    # Skills.
    diffs += compare_tree(REPO_ROOT / ".cursor" / "skills",
                          REPO_ROOT / ".github" / "skills", "skills")

    # Hooks (semantic).
    diffs += compare_hooks(REPO_ROOT / ".cursor" / "hooks.json",
                           REPO_ROOT / ".github" / "hooks")
    return diffs


def build_report(unresolved: list[Diff]) -> str:
    lines = [
        "STOP — do not answer the user's request yet.",
        "AI-DOCS PARITY: the Cursor and Copilot agent docs are OUT OF SYNC "
        f"({len(unresolved)} unresolved difference(s)).",
        "Your FIRST reply this turn MUST be about this and nothing else: (1) tell "
        "the user the docs diverged, (2) show what differs and which side is more "
        "up to date, (3) give a consolidation recommendation, (4) ask how to "
        "consolidate. Only after the user answers may you resume their original "
        "request. If the user approves the divergence, record its signature in "
        ".ai-docs-parity-allow.json (see its schema); that silences it.",
        "Override: the user can resend their message containing the text "
        f"`{ESCAPE_PHRASE}` to allowlist the current differences and proceed.",
        "",
    ]
    for d in unresolved:
        newer = d.newer_side()
        newer_txt = {"cursor": "cursor side is NEWER (higher mtime)",
                     "copilot": "copilot side is NEWER (higher mtime)",
                     None: "mtime tie / undeterminable"}[newer]
        lines.append(f"* [{d.kind}] {d.pair_id}")
        if d.detail and d.kind in ("missing", "hook"):
            lines.append(f"    {d.detail}")
        lines.append(f"    cursor : {d.cursor_path or '(absent)'}")
        lines.append(f"    copilot: {d.github_path or '(absent)'}")
        lines.append(f"    {newer_txt}")
        lines.append(f"    recommend: {_recommend(d, newer)}")
        if d.kind == "content" and d.detail:
            lines.append("    diff (cursor -> copilot):")
            lines.extend("      " + ln for ln in d.detail.split("\n"))
        lines.append(f"    signature: {d.signature()}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _recommend(d: Diff, newer: str | None) -> str:
    if d.kind == "hook":
        return "add the missing hook triple to the lagging side (formats differ by design; mirror the intent)."
    if d.kind == "missing":
        present = "cursor" if d.cursor_path else "copilot"
        return f"file exists only on the {present} side -> mirror it to the other side (or delete both if obsolete)."
    if newer == "cursor":
        return "cursor is newer -> copy cursor -> copilot after confirming the change was intended."
    if newer == "copilot":
        return "copilot is newer -> copy copilot -> cursor after confirming the change was intended."
    return "both sides differ with no clear newer file -> review manually and merge."


# --------------------------------------------------------------------------- #
# Emit / main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="Cursor<->Copilot AI-docs parity checker.")
    ap.add_argument("--emit", choices=["text", "cursor", "copilot"], default="text",
                    help="output contract: text (human), cursor hook, or copilot hook.")
    ap.add_argument("--block", action="store_true",
                    help="enforce: hard-block the turn on unresolved divergence "
                         "(copilot: continue=false). Reads the prompt from stdin so "
                         "the '" + ESCAPE_PHRASE + "' override can release the block.")
    args = ap.parse_args()

    try:
        all_diffs = collect_diffs()
    except Exception as exc:  # fail-safe: never crash the conversation
        msg = f"AI-docs parity check could not run: {exc!r}. Resolve setup, then re-verify."
        return _emit(args.emit, state="error", report=msg, block=args.block)

    allowed = load_allowed_signatures()
    unresolved = [d for d in all_diffs if d.signature() not in allowed]

    if not unresolved:
        report = f"AI-docs parity: OK ({len(all_diffs)} allowed divergence(s) suppressed)." \
            if all_diffs else "AI-docs parity: OK (Cursor and Copilot docs identical)."
        return _emit(args.emit, state="ok", report=report, block=args.block)

    # Escape hatch: user asked to override -> allowlist current divergences, proceed.
    if ESCAPE_RE.search(read_hook_stdin()):
        added = allowlist_add(unresolved)
        report = (f"AI-docs parity: {added} divergence(s) allowlisted via "
                  f"'{ESCAPE_PHRASE}' override. They are now silenced in "
                  ".ai-docs-parity-allow.json.")
        return _emit(args.emit, state="ok", report=report, block=args.block)

    return _emit(args.emit, state="divergent", report=build_report(unresolved),
                 block=args.block)


def _emit(mode: str, state: str, report: str, block: bool) -> int:
    """state: 'ok' | 'divergent' | 'error'."""
    divergent = state != "ok"
    if mode == "copilot":
        if divergent and block:
            # Enforce: halt the turn; the user sees `stopReason` directly, so the
            # alert does not depend on the model choosing to relay it.
            print(json.dumps({"continue": False, "stopReason": report,
                              "systemMessage": report}))
        elif divergent:
            print(json.dumps({"continue": True, "systemMessage": report}))
        else:
            print(json.dumps({"continue": True}))
        return 0
    if mode == "cursor":
        # Cursor surfaces hook stdout to the agent; exit 2 signals "block".
        if divergent:
            print(report)
            return 2 if block else 0
        return 0
    # text (manual runs)
    print(report)
    return 2 if divergent else 0


if __name__ == "__main__":
    sys.exit(main())
