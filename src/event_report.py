"""Bounded summary of a run's events.jsonl (see eventlog.py).

Streams the log line-by-line and prints a compact, size-bounded report so it
never dumps the raw file (which grows to tens of thousands of lines) into a
reader's context. Default view = run anchors + per-op latency + provider/retry
tallies + concurrency + slowest ops. Flags drill into one component or op.

Usage (Windows venv):
    .\\.venv\\Scripts\\python.exe src\\event_report.py <run_dir | events.jsonl>
    ... --component <slug>       ordered timeline for one component
    ... --op <name>              restrict latency/slowest to one op
    ... --tail-over <seconds>    list spans at/over this duration, plus any
                                  still-open op older than it (tagged OPEN)
    ... --top <n>                how many slowest ops to show (default 10)

Mid-flight runs: an op that has a ``start`` record but no matching ``end``
yet (still running, or the process died mid-call) is an *open span*. These
are reported separately in ``== in-flight ==`` (age = time since its start,
measured against the newest ``mono`` timestamp seen in the log -- so this
works whether the process is still alive or not) and folded into
``--tail-over``/concurrency so a hung or slow-but-alive op is visible even
before it ever writes an ``end`` record.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path
from typing import Any, Iterator


def _iter_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield JSON objects one line at a time; skip blank/torn lines."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # torn last line during a live run
            if isinstance(rec, dict):
                yield rec


def _pct(vals: list[float], p: float) -> float | None:
    vals = sorted(vals)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, int(round((p / 100) * (len(vals) - 1)))))
    return vals[k]


def _fmt(x: float | None) -> str:
    return "-" if x is None else f"{x:.1f}"


class Spans:
    """Pair start/end records by op_id into completed spans."""

    def __init__(self) -> None:
        self._open: dict[int, dict[str, Any]] = {}
        self.done: list[dict[str, Any]] = []

    def feed(self, rec: dict[str, Any]) -> None:
        op_id = rec.get("op_id")
        if op_id is None:
            return
        if rec.get("phase") == "start":
            self._open[op_id] = rec
        elif rec.get("phase") == "end":
            start = self._open.pop(op_id, None)
            dur = rec.get("dur_s")
            if dur is None and start is not None:
                dur = round(rec.get("mono", 0.0) - start.get("mono", 0.0), 3)
            self.done.append(
                {
                    "op": rec.get("op"),
                    "stage": rec.get("stage") or (start or {}).get("stage"),
                    "slug": rec.get("slug") or (start or {}).get("slug"),
                    "status": rec.get("status"),
                    "attempt": rec.get("attempt"),
                    "label": rec.get("label") or (start or {}).get("label"),
                    "dur_s": float(dur) if dur is not None else None,
                    "start_mono": (start or {}).get("mono"),
                    "end_mono": rec.get("mono"),
                }
            )

    def open_spans(self) -> list[dict[str, Any]]:
        """Started ops with no matching ``end`` yet -- the in-flight ones."""
        out = []
        for start in self._open.values():
            out.append(
                {
                    "op": start.get("op"),
                    "stage": start.get("stage"),
                    "slug": start.get("slug"),
                    "status": "open",
                    "attempt": start.get("attempt"),
                    "label": start.get("label"),
                    "dur_s": None,
                    "start_mono": start.get("mono"),
                    "end_mono": None,
                }
            )
        return out


def _load_from_records(records: Iterator[dict[str, Any]]) -> dict[str, Any]:
    """Core aggregation, decoupled from file I/O so it's directly testable."""
    spans = Spans()
    points: dict[str, list[dict[str, Any]]] = {}
    retries: dict[str, int] = {}
    cache = {"read_hit": 0, "read_miss": 0, "write": 0}
    total = 0
    now_mono: float | None = None
    last_ts: str | None = None
    for rec in records:
        total += 1
        spans.feed(rec)
        mono = rec.get("mono")
        if isinstance(mono, (int, float)) and (now_mono is None or mono > now_mono):
            now_mono = mono
        if rec.get("ts"):
            last_ts = rec.get("ts")
        op = rec.get("op")
        phase = rec.get("phase")
        if op == "retry":
            retries[str(rec.get("kind"))] = retries.get(str(rec.get("kind")), 0) + 1
        elif op == "cache" and phase == "event":
            if rec.get("kind") == "read":
                cache["read_hit" if rec.get("hit") else "read_miss"] += 1
            elif rec.get("kind") == "write":
                cache["write"] += 1
        elif op in ("run", "preflight", "workers", "first_row", "row_written"):
            points.setdefault(f"{op}:{phase}", []).append(rec)
    return {
        "lines": total,
        "spans": spans.done,
        "open": spans.open_spans(),
        "now_mono": now_mono,
        "last_ts": last_ts,
        "points": points,
        "retries": retries,
        "cache": cache,
    }


def _load(path: Path) -> dict[str, Any]:
    return _load_from_records(_iter_records(path))


def _first(points: dict[str, list[dict[str, Any]]], key: str) -> dict[str, Any] | None:
    got = points.get(key)
    return got[0] if got else None


def _latency_table(spans: list[dict[str, Any]], only_op: str | None) -> list[str]:
    by_op: dict[str, list[float]] = {}
    for s in spans:
        if s["dur_s"] is None:
            continue
        if only_op and s["op"] != only_op:
            continue
        by_op.setdefault(str(s["op"]), []).append(s["dur_s"])
    lines = [
        f"{'op':<20} {'n':>5} {'sum':>9} {'mean':>8} {'med':>8} {'p90':>8} {'max':>8}"
    ]
    for op in sorted(by_op, key=lambda k: -sum(by_op[k])):
        v = by_op[op]
        lines.append(
            f"{op:<20} {len(v):>5} {sum(v):>9.1f} {st.mean(v):>8.1f} "
            f"{_fmt(st.median(v)):>8} {_fmt(_pct(v, 90)):>8} {max(v):>8.1f}"
        )
    return lines


def _status_tally(spans: list[dict[str, Any]], op: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in spans:
        if s["op"] == op:
            out[str(s["status"])] = out.get(str(s["status"]), 0) + 1
    return out


def _concurrency(
    spans: list[dict[str, Any]],
    open_spans: list[dict[str, Any]],
    now_mono: float | None,
    op: str = "component",
) -> str:
    intervals = [
        (s["start_mono"], s["end_mono"])
        for s in spans
        if s["op"] == op and s["start_mono"] is not None and s["end_mono"] is not None
    ]
    open_n = 0
    if now_mono is not None:
        for s in open_spans:
            if s["op"] == op and s["start_mono"] is not None:
                intervals.append((s["start_mono"], now_mono))
                open_n += 1
    if not intervals:
        return "no component spans"
    events: list[tuple[float, int]] = []
    for a, b in intervals:
        events.append((a, 1))
        events.append((b, -1))
    events.sort()
    cur = peak = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    t0 = min(a for a, _ in intervals)
    t1 = max(b for _, b in intervals)
    window = t1 - t0
    busy = sum(b - a for a, b in intervals)
    avg = busy / window if window > 0 else 0.0
    open_note = f"  (incl. {open_n} still-open)" if open_n else ""
    return (
        f"peak={peak}  avg={avg:.1f}  window={window:.0f}s  "
        f"spans={len(intervals)}{open_note}"
    )


def _report(data: dict[str, Any], top: int, only_op: str | None, tail_over: float | None) -> str:
    points = data["points"]
    spans = data["spans"]
    open_spans = data["open"]
    now_mono = data["now_mono"]
    out: list[str] = []

    run_start = _first(points, "run:start")
    run_end = _first(points, "run:end")
    pre = _first(points, "preflight:end")
    workers_start = _first(points, "workers:start")
    workers_end = _first(points, "workers:end")
    first_row = _first(points, "first_row:event")

    out.append("== run ==")
    if run_start:
        out.append(
            f"run_id={run_start.get('run_id')} components={run_start.get('components')} "
            f"model={run_start.get('model')} workers={run_start.get('workers')}"
        )
    status = "COMPLETE" if run_end else "IN FLIGHT (no run:end yet)"
    out.append(f"status: {status}")
    if data.get("last_ts"):
        out.append(f"last event: {data['last_ts']}")
    out.append(f"log lines: {data['lines']}")
    if pre:
        out.append(f"preflight: {_fmt(pre.get('dur_s'))}s")
    if run_end:
        out.append(f"run wall:  {_fmt(run_end.get('dur_s'))}s")
    if workers_end:
        out.append(f"workers:   {_fmt(workers_end.get('dur_s'))}s")
    if workers_start and first_row:
        ttf = first_row.get("mono", 0.0) - workers_start.get("mono", 0.0)
        out.append(f"time-to-first-row: {ttf:.1f}s  (slug={first_row.get('slug')})")

    out.append("")
    out.append("== per-op latency (s) ==")
    out.extend(_latency_table(spans, only_op))

    out.append("")
    out.append("== providers / retries ==")
    out.append(f"claude status: {_status_tally(spans, 'claude')}")
    out.append(f"gpt status:    {_status_tally(spans, 'gpt')}")
    out.append(f"retries:       {data['retries']}")
    out.append(f"cache:         {data['cache']}")

    out.append("")
    out.append("== concurrency (component overlap) ==")
    out.append(_concurrency(spans, open_spans, now_mono))

    out.append("")
    out.append("== in-flight (open spans, age vs last event) ==")
    ages = [
        (round(now_mono - s["start_mono"], 3), s)
        for s in open_spans
        if now_mono is not None and s["start_mono"] is not None
        and (only_op is None or s["op"] == only_op)
    ]
    if not ages:
        out.append("none")
    else:
        ages.sort(key=lambda pair: -pair[0])
        for age, s in ages:
            extra = ""
            if s.get("stage"):
                extra += f" stage={s['stage']}"
            if s.get("label"):
                extra += f" label={s['label']}"
            if s.get("attempt"):
                extra += f" attempt={s['attempt']}"
            out.append(f"{age:>8.1f}s  {s['op']:<18} {s['slug'] or ''}{extra}")

    out.append("")
    if tail_over is not None:
        out.append(f"== spans/open-ops >= {tail_over:g}s ==")
        tail = [
            (s["dur_s"], s, "")
            for s in spans
            if s["dur_s"] is not None and s["dur_s"] >= tail_over
        ]
        tail += [
            (age, s, " [OPEN]")
            for age, s in ages
            if age >= tail_over
        ]
        if only_op:
            tail = [t for t in tail if t[1]["op"] == only_op]
        tail.sort(key=lambda t: -t[0])
        for dur, s, tag in tail[: max(top, len(tail))]:
            out.append(f"{dur:>8.1f}s  {s['op']:<18} {s['slug'] or ''}{tag}")
    else:
        out.append(f"== slowest {top} ops ==")
        pool = [s for s in spans if s["dur_s"] is not None]
        if only_op:
            pool = [s for s in pool if s["op"] == only_op]
        pool.sort(key=lambda s: -s["dur_s"])
        for s in pool[:top]:
            status = f" [{s['status']}]" if s["status"] not in (None, "ok") else ""
            out.append(f"{s['dur_s']:>8.1f}s  {s['op']:<18} {s['slug'] or ''}{status}")
    return "\n".join(out)


def _component_timeline(path: Path, slug: str) -> str:
    recs = [r for r in _iter_records(path) if r.get("slug") == slug]
    if not recs:
        return f"no events for slug={slug!r}"
    recs.sort(key=lambda r: r.get("seq", 0))
    t0 = recs[0].get("mono", 0.0)
    out = [f"== timeline: {slug} ({len(recs)} events) =="]
    for r in recs:
        rel = r.get("mono", 0.0) - t0
        dur = f" dur={r['dur_s']:.1f}s" if r.get("dur_s") is not None else ""
        extra = ""
        if r.get("status") not in (None, "ok"):
            extra += f" status={r.get('status')}"
        if r.get("attempt"):
            extra += f" attempt={r.get('attempt')}"
        if r.get("label"):
            extra += f" label={r.get('label')}"
        out.append(
            f"{rel:>8.1f}s  {str(r.get('op')):<18} {str(r.get('phase')):<6}{dur}{extra}"
        )
    return "\n".join(out)


def _resolve(path_arg: str) -> Path:
    p = Path(path_arg)
    if p.is_dir():
        return p / "events.jsonl"
    return p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize a run's events.jsonl")
    parser.add_argument("path", help="run dir or events.jsonl path")
    parser.add_argument("--component", help="print ordered timeline for one slug")
    parser.add_argument("--op", help="restrict latency/slowest to one op name")
    parser.add_argument("--tail-over", type=float, help="list spans at/over N seconds")
    parser.add_argument("--top", type=int, default=10, help="slowest ops to show")
    args = parser.parse_args(argv)

    path = _resolve(args.path)
    if not path.is_file():
        print(f"no event log at {path}", file=sys.stderr)
        return 2

    if args.component:
        print(_component_timeline(path, args.component))
        return 0

    data = _load(path)
    print(_report(data, top=args.top, only_op=args.op, tail_over=args.tail_over))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
