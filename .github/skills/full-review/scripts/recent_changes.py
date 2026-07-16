#!/usr/bin/env python3
"""Census: git churn — how often each file changed, from `git log` on stdin.

This script never runs git itself. You (or the user) run the git command
explicitly — so approving this script can never run an arbitrary command —
and pipe its output in:

    git log --since="30 days ago" --name-only --pretty=format: \\
        | python recent_changes.py --max-touches 10

Input: `git log --name-only --pretty=format:` output on stdin (one changed
path per line, blank lines between commits are ignored).
Output: TSV `touches<TAB>path`, sorted by touches desc, then path asc.
Exit codes: 0 = no breach, 1 = --max-touches breached, 2 = usage error.
"""
import argparse
import sys
from collections import Counter


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-touches", type=int, default=-1,
                        help="breach when any file's touches exceed this; -1 = report-only (default)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except AttributeError:
        pass

    counts = Counter(line for line in sys.stdin.read().splitlines() if line.strip())
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    print("touches\tpath")
    for path, touches in rows:
        print(f"{touches}\t{path}")

    breached = args.max_touches >= 0 and any(t > args.max_touches for _, t in rows)
    return 1 if breached else 0


if __name__ == "__main__":
    sys.exit(main())
