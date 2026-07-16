#!/usr/bin/env python3
"""Census: regex hits for risky constructs, patterns from a JSON config.

Output: TSV `name<TAB>path<TAB>line<TAB>text`, sorted by path asc, line asc,
then name asc. Config: risky_patterns.json next to this script, or --config.
Hits are review pointers, not verdicts — expect false positives.
Exit codes: 0 = no breach, 1 = --max-count breached, 2 = usage/environment
error (missing/invalid config, bad regex, bad path).
"""
import argparse
import json
import os
import re
import sys

EXCLUDED_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "target", "out",
    ".venv", "venv", "__pycache__", ".tox", ".next", ".nuxt", "coverage",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


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


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories (default: .)")
    parser.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "risky_patterns.json"),
        help="pattern config JSON (default: risky_patterns.json beside this script)")
    parser.add_argument("--max-count", type=int, default=-1,
                        help="breach when total hits exceed this; -1 = report-only (default)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except AttributeError:
        pass

    try:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
        patterns = [(p["name"], re.compile(p["regex"])) for p in config["patterns"]]
    except (OSError, ValueError, KeyError, re.error) as e:
        print(f"error: bad config {args.config}: {e}", file=sys.stderr)
        return 2

    for p in args.paths or ["."]:
        if not os.path.exists(p):
            print(f"error: no such path: {p}", file=sys.stderr)
            return 2

    self_paths = {os.path.abspath(__file__), os.path.abspath(args.config)}
    rows = []
    for path in walk_files(args.paths or ["."]):
        if os.path.abspath(path) in self_paths or is_binary(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    for name, rx in patterns:
                        if rx.search(line):
                            rows.append((norm(path), lineno, name, line.strip()[:100]))
        except OSError:
            continue

    rows.sort(key=lambda r: (r[0], r[1], r[2]))

    print("name\tpath\tline\ttext")
    for path, lineno, name, text in rows:
        print(f"{name}\t{path}\t{lineno}\t{text}")

    return 1 if 0 <= args.max_count < len(rows) else 0


if __name__ == "__main__":
    sys.exit(main())
