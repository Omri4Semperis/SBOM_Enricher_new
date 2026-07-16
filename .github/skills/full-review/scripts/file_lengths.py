#!/usr/bin/env python3
"""Census: line count per text file. Breach = any file over --max-lines.

Output: TSV `lines<TAB>path`, sorted by lines desc, then path asc.
Exit codes: 0 = no breach, 1 = threshold breached, 2 = usage/environment error.
"""
import argparse
import os
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
    parser.add_argument("--max-lines", type=int, default=400, help="breach threshold (default: 400)")
    parser.add_argument("--all", action="store_true", help="list every file, not only breaches")
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
                count = sum(1 for _ in f)
        except OSError:
            continue
        rows.append((count, norm(path)))

    rows.sort(key=lambda r: (-r[0], r[1]))
    breaches = [r for r in rows if r[0] > args.max_lines]

    print("lines\tpath")
    for count, path in (rows if args.all else breaches):
        print(f"{count}\t{path}")

    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
