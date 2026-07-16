"""Global, concurrency-safe JSONL event log with correlation IDs.

One process-wide append-only log (``runs/<run>/events.jsonl``), one JSON object
per line, flushed per record so a hung run still shows the last in-flight op.
Records carry correlation IDs (run/component/slot/op) sourced from contextvars,
so nested operations inherit their component/slot without threading params
through every call -- contextvars propagate across ``await`` and, because
``asyncio.to_thread`` copies the context, across worker threads too.

Uninitialised = no-op: unit tests and fakes that never call ``init_event_log``
emit nothing and pay almost no cost.
"""

from __future__ import annotations

import contextvars
import json
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- correlation context (auto-attached to every record) -------------------
_comp_idx: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "eventlog_comp_idx", default=None
)
_slug: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "eventlog_slug", default=None
)
_slot_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "eventlog_slot_id", default=None
)
_stage: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "eventlog_stage", default=None
)

_id_lock = threading.Lock()
_op_seq = 0
_rec_seq = 0


def _next_id(kind: str) -> int:
    """Monotonic, thread-safe counter. ``kind`` is 'op' or 'rec'."""
    global _op_seq, _rec_seq
    with _id_lock:
        if kind == "op":
            _op_seq += 1
            return _op_seq
        _rec_seq += 1
        return _rec_seq


def next_op_id() -> int:
    """Allocate a unique operation id for a manual start/end span pair."""
    return _next_id("op")


class EventLog:
    """Lock-guarded, per-record-flushed JSONL writer (thread-safe)."""

    def __init__(self, path: Path, run_id: str) -> None:
        self._path = Path(path)
        self._run_id = run_id
        self._lock = threading.Lock()
        self._fh = self._path.open("a", encoding="utf-8")

    def emit(self, op: str, phase: str, **fields: Any) -> None:
        rec: dict[str, Any] = {
            "seq": _next_id("rec"),
            "ts": datetime.now(timezone.utc).isoformat(),
            "mono": time.perf_counter(),
            "run_id": self._run_id,
            "comp_idx": _comp_idx.get(),
            "slug": _slug.get(),
            "slot_id": _slot_id.get(),
            "stage": _stage.get(),
            "op": op,
            "phase": phase,
        }
        rec.update(fields)
        line = json.dumps(rec, ensure_ascii=False, default=str)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:  # noqa: BLE001 - best-effort close
                pass


_log: EventLog | None = None


def init_event_log(path: Path | str, run_id: str) -> EventLog:
    """Open (replacing any prior) the process-wide event log."""
    global _log
    if _log is not None:
        _log.close()
    _log = EventLog(Path(path), run_id)
    return _log


def close_event_log() -> None:
    global _log
    if _log is not None:
        _log.close()
        _log = None


def emit(op: str, phase: str = "event", **fields: Any) -> None:
    """Emit one record. No-op if the log was never initialised."""
    if _log is not None:
        _log.emit(op, phase, **fields)


# --- correlation-context setters -------------------------------------------
@contextmanager
def component_context(comp_idx: int, slug: str):
    tok_i = _comp_idx.set(comp_idx)
    tok_s = _slug.set(slug)
    try:
        yield
    finally:
        _comp_idx.reset(tok_i)
        _slug.reset(tok_s)


@contextmanager
def slot_context(slot_id: int):
    tok = _slot_id.set(slot_id)
    try:
        yield
    finally:
        _slot_id.reset(tok)


@asynccontextmanager
async def log_op(op: str, **fields: Any):
    """Wrap a stage: emit start, then end with duration + ok/error status.

    Also sets the ``stage`` contextvar for the body's lifetime, so provider
    attempt spans nested inside inherit their enclosing stage name.
    """
    op_id = next_op_id()
    tok = _stage.set(op)
    start = time.perf_counter()
    emit(op, "start", op_id=op_id, **fields)
    try:
        yield op_id
    except BaseException as exc:
        emit(
            op,
            "end",
            op_id=op_id,
            dur_s=round(time.perf_counter() - start, 3),
            status="error",
            error=type(exc).__name__,
        )
        raise
    else:
        emit(
            op,
            "end",
            op_id=op_id,
            dur_s=round(time.perf_counter() - start, 3),
            status="ok",
        )
    finally:
        _stage.reset(tok)
