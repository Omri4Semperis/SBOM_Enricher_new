"""Live progress bar + ETA for the worker pool."""

from __future__ import annotations

import sys
import threading
import time


def progress_bar(done: int, total: int, width: int = 35, failed: int = 0) -> str:
    filled = int(width * done / total) if total else 0
    failures = f" ({failed} failed)" if failed else ""
    return f"[{'█' * filled}{'░' * (width - filled)}] {done}/{total}{failures}"


def format_eta(done: int, total: int, elapsed_s: float) -> str:
    if done <= 0 or total <= 0:
        return "ETA --"
    if done >= total:
        return f"done in {elapsed_s:.0f}s"
    rate = done / elapsed_s if elapsed_s > 0 else 0.0
    if rate <= 0:
        return "ETA --"
    remaining = (total - done) / rate
    return f"ETA {remaining:.0f}s"


def render_line(done: int, total: int, elapsed_s: float, failed: int = 0) -> str:
    # Pad ETA so \r redraws don't leave leftover chars (e.g. "21sss").
    eta = f"{format_eta(done, total, elapsed_s):<16}"
    return f"  {progress_bar(done, total, failed=failed)}  {eta}"


class Progress:
    """Thread/async-safe completed-component counter with live stderr redraw."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self.failed = 0
        self._lock = threading.Lock()
        self._t0 = time.perf_counter()

    def tick(self, *, failed: bool = False) -> None:
        with self._lock:
            self.done += 1
            self.failed += failed
            done, total, failures = self.done, self.total, self.failed
            elapsed = time.perf_counter() - self._t0
        line = render_line(done, total, elapsed, failures)
        print(f"\r{line}", end="", file=sys.stderr, flush=True)
        if done >= total:
            print(file=sys.stderr)

    def start(self) -> None:
        print(f"\r{render_line(0, self.total, 0.0)}", end="", file=sys.stderr, flush=True)
