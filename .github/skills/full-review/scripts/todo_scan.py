#!/usr/bin/env python3
"""Census: TODO/FIXME/HACK/XXX markers. Breach = total hits over --max-count (if set).

Output: TSV `path<TAB>line<TAB>tag<TAB>text`, sorted by path asc, then line asc.
Exit codes: 0 = no breach, 1 = threshold breached, 2 = usage/environment error.
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

TAG_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")


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
    parser.add_argument("--max-count", type=int, default=-1,
                        help="breach when total hits exceed this; -1 = report-only (default)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except AttributeError:
        pass

    for p in args.paths or ["."]:
        if not os.path.exists(p):
            print(f"error: no such path: {p}", file=sys.stderr)
            return 2

    rows = []
    for path in walk_files(args.paths or ["."]):
        if is_binary(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    m = TAG_RE.search(line)
                    if m:
                        rows.append((norm(path), lineno, m.group(1), line.strip()[:120]))
        except OSError:
            continue

    rows.sort(key=lambda r: (r[0], r[1]))

    print("path\tline\ttag\ttext")
    for path, lineno, tag, text in rows:
        print(f"{path}\t{lineno}\t{tag}\t{text}")

    return 1 if 0 <= args.max_count < len(rows) else 0


if __name__ == "__main__":
    sys.exit(main())
