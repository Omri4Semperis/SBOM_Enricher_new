#!/usr/bin/env python3
"""Thin forwarder — report logic lives in src/runtime_report.py.

Prefer the product entrypoint:

    .\\.venv\\Scripts\\python.exe src\\runtime_report.py <run_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from runtime_report import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
