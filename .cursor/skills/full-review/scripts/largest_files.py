#!/usr/bin/env python3
"""Census: largest files by size. Breach = any file over --max-kb.

Output: TSV `bytes<TAB>path` for the top --top files, sorted by bytes desc,
then path asc. Binary files included (big blobs are the point).
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
    parser.add_argument("--top", type=int, default=20, help="how many files to list (default: 20)")
    parser.add_argument("--max-kb", type=int, default=1024, help="breach threshold in KiB (default: 1024)")
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
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        rows.append((size, norm(path)))

    rows.sort(key=lambda r: (-r[0], r[1]))
    breaches = [r for r in rows if r[0] > args.max_kb * 1024]

    print("bytes\tpath")
    for size, path in rows[: args.top]:
        print(f"{size}\t{path}")

    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
