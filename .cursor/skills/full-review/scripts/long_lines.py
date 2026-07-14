#!/usr/bin/env python3
"""Census: lines longer than --max-length characters. Breach = any hit.

Output: TSV `path<TAB>line<TAB>length`, sorted by path asc, then line asc.
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
    parser.add_argument("--max-length", type=int, default=160, help="breach threshold in characters (default: 160)")
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
                    length = len(line.rstrip("\r\n"))
                    if length > args.max_length:
                        rows.append((norm(path), lineno, length))
        except OSError:
            continue

    rows.sort(key=lambda r: (r[0], r[1]))

    print("path\tline\tlength")
    for path, lineno, length in rows:
        print(f"{path}\t{lineno}\t{length}")

    return 1 if rows else 0


if __name__ == "__main__":
    sys.exit(main())
