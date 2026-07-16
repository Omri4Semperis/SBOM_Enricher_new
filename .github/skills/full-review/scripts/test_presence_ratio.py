#!/usr/bin/env python3
"""Census: ratio of test files to source files. Breach = ratio under --min-ratio.

Output: one JSON object, sorted keys: {"ratio": r, "source_files": N, "test_files": M}.
source_files excludes test files (counts are disjoint).
Exit codes: 0 = no breach, 1 = threshold breached, 2 = usage/environment error.
"""
import argparse
import json
import os
import sys

EXCLUDED_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "target", "out",
    ".venv", "venv", "__pycache__", ".tox", ".next", ".nuxt", "coverage",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

SOURCE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".go", ".rb", ".rs",
    ".java", ".kt", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".php",
    ".swift", ".scala", ".sh", ".ps1", ".pl", ".lua", ".ex", ".exs",
}

TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testdata"}


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


def is_test(path):
    name = os.path.basename(path)
    stem, ext = os.path.splitext(name)
    if name.startswith("test_") or stem == "conftest":
        return True
    if stem.endswith(("_test", "_spec")) or stem.endswith((".test", ".spec")):
        return True
    return bool(set(norm(path).split("/")[:-1]) & TEST_DIRS)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", default=["."], help="files or directories (default: .)")
    parser.add_argument("--min-ratio", type=float, default=0.1,
                        help="breach when test/source ratio is below this (default: 0.1)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except AttributeError:
        pass

    for p in args.paths or ["."]:
        if not os.path.exists(p):
            print(f"error: no such path: {p}", file=sys.stderr)
            return 2

    source = tests = 0
    for path in walk_files(args.paths or ["."]):
        if os.path.splitext(path)[1].lower() not in SOURCE_EXTS:
            continue
        if is_test(path):
            tests += 1
        else:
            source += 1

    ratio = round(tests / source, 4) if source else 0.0
    print(json.dumps({"ratio": ratio, "source_files": source, "test_files": tests}, sort_keys=True))

    return 1 if source > 0 and ratio < args.min_ratio else 0


if __name__ == "__main__":
    sys.exit(main())
