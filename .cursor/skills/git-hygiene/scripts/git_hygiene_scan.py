#!/usr/bin/env python3
"""Census: staged/tracked/untracked files that probably shouldn't be in git.

Rules come from rules.json in the skill directory (or --config). The agent
edits that file's "allow" list when the user blesses a kind — this script
only reports; it never edits .gitignore or anything else.

Interactive mode reads the file lists on stdin as `kind<TAB>path` lines
(kind is staged, tracked, or untracked). The agent gathers them by running
the read-only git commands the user approves (see SKILL.md), so interactive
runs never shell out — approving this script can't run an arbitrary command.

Output: TSV `kind<TAB>rule<TAB>path`; kind is staged|tracked|untracked
(one row per path, priority staged > tracked > untracked), sorted by kind
priority then path.
Exit codes: 0 = clean, 1 = findings, 2 = usage/environment error.
--hook mode (Cursor beforeShellExecution / preToolUse, or legacy Claude
PreToolUse): reads the hook JSON on stdin; if the command is a `git commit`,
it asks git for the staged files itself (the one place this script runs git,
because a commit hook can't pause for approval) and scans them — findings
block the commit (exit 2 + Cursor permission-deny JSON on stdout; summary on
stderr); everything else, including scanner errors, exits 0 so a buggy
scanner never breaks commits.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from typing import Any, Iterable, TypedDict

KIND_RANK = {"staged": 0, "tracked": 1, "untracked": 2}


class Rules(TypedDict):
    dirs: set[str]
    exts: set[str]
    files: set[str]
    secrets: list[str]
    max_kb: int
    allow: list[str]


def git_lines(root: str, *args: str) -> list[str]:
    """Read-only git query. Used ONLY by --hook mode.

    The hook runs non-interactively (on every agent `git commit`), so it
    cannot defer to a user-approved command the way interactive mode does — it
    has to ask git for the staged files itself. This subprocess is deliberately
    narrow: a fixed `git` executable, list-form args (never a shell string, so
    no injection), and only read-only queries. Interactive scans never reach
    here — they take their file lists from stdin (see main).
    """
    result = subprocess.run(["git", "-C", root, *args],
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def load_rules(path: str) -> Rules:
    with open(path, "r", encoding="utf-8") as f:
        cfg: Any = json.load(f)
    allow: list[str] = []
    for entry in cfg.get("allow", []):
        if isinstance(entry, str):
            allow.append(entry)
        elif hasattr(entry, "get") and isinstance(entry.get("pattern"), str):
            allow.append(entry["pattern"])
    return {
        "dirs": set(cfg.get("warn_dirs", [])),
        "exts": set(cfg.get("warn_extensions", [])),
        "files": set(cfg.get("warn_files", [])),
        "secrets": list(cfg.get("secret_patterns", [])),
        "max_kb": int(cfg.get("max_kb", 1024)),
        "allow": allow,
    }


def match_rule(path: str, root: str, rules: Rules) -> str | None:
    """First matching rule wins; secrets outrank everything."""
    name = path.rsplit("/", 1)[-1]
    for pat in rules["secrets"]:
        if fnmatch.fnmatch(name, pat):
            return f"secret:{pat}"
    for part in path.split("/")[:-1]:
        if part in rules["dirs"]:
            return f"dir:{part}"
    ext = os.path.splitext(name)[1].lower()
    if ext in rules["exts"]:
        return f"ext:{ext}"
    if name in rules["files"]:
        return f"file:{name}"
    full = os.path.join(root, path)
    try:
        kb = os.path.getsize(full) // 1024
        if kb > rules["max_kb"]:
            return f"size:{kb}kb>{rules['max_kb']}kb"
    except OSError:
        pass
    return None


def allowed(path: str, rules: Rules) -> bool:
    return any(fnmatch.fnmatch(path, pat) or
               fnmatch.fnmatch(path.rsplit("/", 1)[-1], pat)
               for pat in rules["allow"])


def scan(entries: Iterable[tuple[str, str]], root: str,
         rules: Rules) -> list[tuple[str, str, str]]:
    """Apply rules to (kind, path) entries. Dedup keeps the highest-priority
    kind (staged > tracked > untracked); entries are pre-sorted so order in
    doesn't matter."""
    seen: set[str] = set()
    rows: list[tuple[str, str, str]] = []
    for kind, path in sorted(entries, key=lambda e: KIND_RANK.get(e[0], 99)):
        path = path.strip().strip('"').replace("\\", "/")
        if not path or path in seen:
            continue
        seen.add(path)
        if allowed(path, rules):
            continue
        rule = match_rule(path, root, rules)
        if rule:
            rows.append((kind, rule, path))
    rows.sort(key=lambda r: (KIND_RANK[r[0]], r[2]))
    return rows


def read_entries(stream: Any) -> list[tuple[str, str]]:
    """Interactive input: `kind<TAB>path` lines on stdin (kind is staged,
    tracked, or untracked; an unlabeled line counts as tracked). The agent
    produces these by running the read-only git commands the user approves
    (see SKILL.md), so interactive mode never runs git itself."""
    entries: list[tuple[str, str]] = []
    for line in stream.read().splitlines():
        line = line.rstrip("\r")
        if not line.strip():
            continue
        kind, sep, path = line.partition("\t")
        if sep and kind.strip() in KIND_RANK:
            entries.append((kind.strip(), path))
        else:
            entries.append(("tracked", line))
    return entries


def _hook_command(payload: Any) -> str:
    """Extract the shell command from Cursor or Claude hook JSON."""
    # Cursor beforeShellExecution / beforeMCPExecution
    if isinstance(payload.get("command"), str) and payload.get("command"):
        return payload["command"]
    tool_input: Any = payload.get("tool_input") or {}
    if isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
        return tool_input["command"]
    return ""


def _hook_relevant(payload: Any, command: str) -> bool:
    """True when this payload is a shell/bash tool about to run something."""
    event = str(payload.get("hook_event_name") or "")
    if event in ("beforeShellExecution", "beforeMCPExecution"):
        return True
    tool = str(payload.get("tool_name") or "")
    # Cursor: Shell; Claude Code legacy: Bash
    if tool in ("Shell", "Bash"):
        return True
    # Cursor preToolUse with Shell matcher may still set tool_name
    if command and not tool:
        return True
    return False


def _hook_cwd(payload: Any) -> str:
    if payload.get("cwd"):
        return str(payload["cwd"])
    roots = payload.get("workspace_roots") or []
    if isinstance(roots, list) and roots:
        return str(roots[0])
    return os.getcwd()


def hook_mode(config_path: str) -> int:
    try:
        payload: Any = json.load(sys.stdin)
        command = _hook_command(payload)
        if not _hook_relevant(payload, command):
            return 0
        if not re.search(r"\bgit\b[^|;&]*\bcommit\b", command):
            return 0
        root = _hook_cwd(payload)
        staged = [("staged", p)
                  for p in git_lines(root, "diff", "--cached", "--name-only")]
        rows = scan(staged, root, load_rules(config_path))
    except Exception as e:  # never break commits on scanner bugs
        print(f"git_hygiene_scan: skipped ({e})", file=sys.stderr)
        return 0
    if not rows:
        return 0
    lines = "\n".join(f"  {rule}  {path}" for _, rule, path in rows[:20])
    more = f"\n  ...and {len(rows) - 20} more" if len(rows) > 20 else ""
    msg = (
        "git-hygiene: staged files look like they don't belong in git:\n"
        f"{lines}{more}\n"
        "Run the git-hygiene skill: propose .gitignore entries to the user, "
        "or record user-approved kinds in its rules.json 'allow' list, then "
        "retry the commit."
    )
    print(msg, file=sys.stderr)
    # Cursor beforeShellExecution / preToolUse prefer JSON permission deny;
    # exit 2 also blocks (shared with Claude Code).
    print(json.dumps({
        "permission": "deny",
        "user_message": "git-hygiene blocked this commit — junk appears staged.",
        "agent_message": msg,
    }))
    return 2


def main() -> int:
    default_config = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules.json")
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("path", nargs="?", default=".", help="repo root (default: .)")
    parser.add_argument("--config", default=default_config,
                        help="rules JSON (default: rules.json in the skill directory)")
    parser.add_argument("--hook", action="store_true",
                        help="Hook mode: JSON on stdin, exit 2 blocks the commit")
    args = parser.parse_args()

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", newline="\n")

    if args.hook:
        return hook_mode(args.config)

    try:
        rules = load_rules(args.config)
    except (OSError, ValueError, KeyError) as e:
        print(f"error: bad config {args.config}: {e}", file=sys.stderr)
        return 2
    rows = scan(read_entries(sys.stdin), args.path, rules)

    print("kind\trule\tpath")
    for kind, rule, path in rows:
        print(f"{kind}\t{rule}\t{path}")
    return 1 if rows else 0


if __name__ == "__main__":
    sys.exit(main())
