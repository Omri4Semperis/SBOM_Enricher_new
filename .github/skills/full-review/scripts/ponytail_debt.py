#!/usr/bin/env python3
"""Census: harvest `ponytail:` shortcut markers into a debt ledger.

The ponytail skill marks each deliberate shortcut with a comment
`ponytail: <ceiling>, <upgrade trigger>`. This finds them so a deferral
can't quietly become permanent. Markers with no upgrade trigger (no comma,
or nothing after it) are the silent-rot risk and show `[no-trigger]`.

Output: TSV `path<TAB>line<TAB>upgrade<TAB>ceiling`, sorted by path asc,
line asc. `.md` files are skipped (the `#` marker collides with markdown
headings and prose that merely mentions the convention).
Exit codes: 0 = clean, 1 = a threshold breached, 2 = usage/environment error.
"""
import argparse
import os
import re
import sys

EXCLUDED_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "target", "out",
    ".venv", "venv", "__pycache__", ".tox", ".next", ".nuxt", "coverage",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

# A comment marker, then `ponytail:`, then the payload to end of line.
MARKER_RE = re.compile(r"(?:#|//|--|;|\*|<!--)\s*ponytail:\s*(.*)")


def is_binary(path):
    try:
        with open(path, "rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def walk_files(roots):
    for root in roots:
        if os.path.isfile(root):
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
            for name in sorted(filenames):
                yield os.path.join(dirpath, name)


def norm(path):
    return os.path.relpath(path).replace(os.sep, "/")


def parse_payload(payload):
    """Return (ceiling, upgrade). upgrade is '[no-trigger]' when absent."""
    payload = payload.strip()
    if payload.endswith("-->"):
        payload = payload[:-3].strip()
    if "," in payload:
        ceiling, upgrade = payload.rsplit(",", 1)
        ceiling, upgrade = ceiling.strip(), upgrade.strip()
        if not upgrade:
            upgrade = "[no-trigger]"
    else:
        ceiling, upgrade = payload, "[no-trigger]"
    return ceiling[:100], upgrade[:80]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories (default: .)")
    parser.add_argument("--max-count", type=int, default=-1,
                        help="breach when total markers exceed this; -1 = report-only (default)")
    parser.add_argument("--fail-on-no-trigger", action="store_true",
                        help="breach if any marker names no upgrade trigger")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except AttributeError:
        pass

    for p in args.paths or ["."]:
        if not os.path.exists(p):
            print(f"error: no such path: {p}", file=sys.stderr)
            return 2

    self_path = os.path.abspath(__file__)
    rows = []
    for path in walk_files(args.paths or ["."]):
        if os.path.abspath(path) == self_path:
            continue  # this file's own regex source contains the marker
        if path.lower().endswith(".md") or is_binary(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    m = MARKER_RE.search(line)
                    if m:
                        ceiling, upgrade = parse_payload(m.group(1))
                        rows.append((norm(path), lineno, upgrade, ceiling))
        except OSError:
            continue

    rows.sort(key=lambda r: (r[0], r[1]))

    print("path\tline\tupgrade\tceiling")
    for path, lineno, upgrade, ceiling in rows:
        print(f"{path}\t{lineno}\t{upgrade}\t{ceiling}")

    no_trigger = sum(1 for r in rows if r[2] == "[no-trigger]")
    breach = (0 <= args.max_count < len(rows)) or (args.fail_on_no_trigger and no_trigger)
    return 1 if breach else 0


if __name__ == "__main__":
    sys.exit(main())
